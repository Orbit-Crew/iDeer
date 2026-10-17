"""
LibreOffice 监听进程管理器

通过启动常驻的 LibreOffice 监听进程，避免每次文档转换时启动新进程的开销
从而大幅提高 Office 文档转 PDF 的速度
"""

import logging
import os
import subprocess
import time

logger = logging.getLogger(__name__)

# LibreOffice 在无输出场景下也可能偶尔打印日志，监听进程是常驻进程，
# stdout/stderr 若接 PIPE 而无人读取，缓冲区写满后进程会永久阻塞——
# 因此监听进程统一重定向到 DEVNULL，绝不用 PIPE。
# 启动等待改为轮询：进程秒退（如端口冲突）能在第一个轮询周期内被发现，
# 而不是无条件阻塞固定秒数。
_LISTENER_STARTUP_WAIT_SECONDS = 2.0
_LISTENER_STARTUP_POLL_SECONDS = 0.1


class LibreOfficeManager:
    """LibreOffice 监听进程管理器（单例模式）"""

    _instance = None
    _listener_process = None
    _listener_port = 8109

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化管理器"""
        if not hasattr(self, "initialized"):
            self.soffice_path = None
            self.initialized = True

    @staticmethod
    def get_instance() -> "LibreOfficeManager":
        """获取管理器单例"""
        if LibreOfficeManager._instance is None:
            LibreOfficeManager._instance = LibreOfficeManager()
        return LibreOfficeManager._instance

    def _find_soffice(self) -> str | None:
        """查找 LibreOffice/OpenOffice 可执行文件"""
        if self.soffice_path:
            return self.soffice_path

        # 常见 LibreOffice/OpenOffice 路径
        possible_paths = [
            # Linux
            "/usr/bin/soffice",
            "/usr/lib/libreoffice/program/soffice",
            "/opt/libreoffice25.2/program/soffice",
            "/opt/libreoffice/program/soffice",
            # macOS
            "/Applications/LibreOffice.app/Contents/MacOS/soffice",
            # Windows
            "C:\\Program Files\\LibreOffice\\program\\soffice.exe",
            "C:\\Program Files (x86)\\LibreOffice\\program\\soffice.exe",
        ]

        # 检查环境变量
        env_path = os.environ.get("LIBREOFFICE_PATH")
        if env_path and os.path.exists(env_path):
            self.soffice_path = env_path
            return env_path

        # 检查常见路径
        for path in possible_paths:
            if os.path.exists(path):
                self.soffice_path = path
                return path

        # 在 PATH 中查找
        try:
            result = subprocess.run(["which", "soffice"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                self.soffice_path = result.stdout.strip()
                return self.soffice_path
        except Exception:
            pass

        return None

    def ensure_listener(self) -> bool:
        """
        确保 LibreOffice 监听进程正在运行

        Returns:
            bool: 是否成功启动或已经在运行
        """
        # 如果已经有监听进程在运行，检查其状态
        if self._listener_process is not None:
            try:
                poll_result = self._listener_process.poll()
                if poll_result is None:  # None 表示进程还在运行
                    logger.debug("LibreOffice 监听进程已在运行")
                    return True
                else:
                    logger.warning(f"LibreOffice 监听进程已退出（退出码: {poll_result}），将重新启动")
                    self._listener_process = None
            except Exception as e:
                logger.warning(f"检查 LibreOffice 监听进程失败: {e}")
                self._listener_process = None

        # 查找 LibreOffice 可执行文件
        soffice_path = self._find_soffice()
        if not soffice_path:
            logger.error("未找到 LibreOffice，无法启动监听进程")
            return False

        try:
            # 启动 LibreOffice 监听进程
            # 注意：--accept 参数格式必须为 --accept=socket,host=localhost,port=8100;urp
            cmd = [
                soffice_path,
                "--headless",  # 无界面模式
                f"--accept=socket,host=localhost,port={self._listener_port};urp",
                "--invisible",  # 后台运行
                "--nocrashreport",  # 不生成崩溃报告
                "--nodefault",  # 不启动默认模板
            ]

            logger.info(f"启动 LibreOffice 监听进程: {' '.join(cmd)}")
            self._listener_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # 轮询等待进程启动：发现进程秒退立即失败，进程存活则等到等待窗口结束
            deadline = time.monotonic() + _LISTENER_STARTUP_WAIT_SECONDS
            while self._listener_process.poll() is None and time.monotonic() < deadline:
                time.sleep(_LISTENER_STARTUP_POLL_SECONDS)

            # 检查进程是否成功启动
            poll_result = self._listener_process.poll()
            if poll_result is not None:
                # 进程已退出（输出已重定向 DEVNULL，仅记录退出码）
                logger.error(f"LibreOffice 监听进程启动失败（退出码: {poll_result}）")
                self._listener_process = None
                return False

            logger.info(f"LibreOffice 监听进程启动成功 (PID: {self._listener_process.pid}, 端口: {self._listener_port})")
            return True

        except Exception as e:
            logger.error(f"启动 LibreOffice 监听进程失败: {e}")
            logger.exception("详细堆栈:")
            self._listener_process = None
            return False

    def stop_listener(self):
        """停止 LibreOffice 监听进程"""
        if self._listener_process is not None:
            try:
                poll_result = self._listener_process.poll()
                if poll_result is None:  # 进程还在运行
                    logger.info(f"停止 LibreOffice 监听进程 (PID: {self._listener_process.pid})")
                    self._listener_process.terminate()
                    try:
                        self._listener_process.wait(timeout=10)
                        logger.info("LibreOffice 监听进程已停止")
                    except subprocess.TimeoutExpired:
                        logger.warning("LibreOffice 监听进程未在 10 秒内停止，强制结束")
                        self._listener_process.kill()
            except Exception as e:
                logger.error(f"停止 LibreOffice 监听进程失败: {e}")
            finally:
                self._listener_process = None

    def _convert_with_fallback(self, cmd: list[str], *, use_listener: bool, timeout: int) -> subprocess.CompletedProcess | None:
        """执行一次转换命令，监听模式失败后回退到普通模式重试一次。

        回退是有界的两段循环而不是递归：监听进程重启可能持续成功而转换
        持续失败，递归自调用会无界增长。返回最后一次尝试的结果；两段都
        超时返回 None（超时已在此记录日志）。
        """
        for attempt_listener in [True, False] if use_listener else [False]:
            actual_timeout = timeout if attempt_listener else 120
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=actual_timeout)
            except subprocess.TimeoutExpired:
                if not attempt_listener:
                    logger.error(f"文档转换超时（{actual_timeout}秒）")
                    return None
                logger.warning("监听进程模式超时，停止监听进程并回退到普通模式重新转换...")
                self.stop_listener()
                continue
            if result.returncode != 0 and attempt_listener:
                logger.warning("监听进程模式失败（退出码 %s），停止监听进程并回退到普通模式重新转换...", result.returncode)
                self.stop_listener()
                continue
            return result
        return None

    def convert_to_pdf(self, file_path: str, output_dir: str, timeout: int = 60) -> str | None:
        """
        使用 LibreOffice 转换文档为 PDF

        优先使用监听进程（更快），如果监听进程不可用则回退到普通模式

        Args:
            file_path: Office 文档路径
            output_dir: 输出目录
            timeout: 超时时间（秒）

        Returns:
            PDF 文件路径，失败返回 None
        """
        from pathlib import Path

        soffice_path = self._find_soffice()
        if not soffice_path:
            return None

        # 尝试使用监听进程（更快）
        use_listener = self.ensure_listener()
        if use_listener:
            logger.info("使用 LibreOffice 监听进程模式转换文档")
        else:
            logger.warning("LibreOffice 监听进程不可用，使用普通模式（较慢）")

        try:
            # 创建输出目录
            os.makedirs(output_dir, exist_ok=True)

            # 构建转换命令（监听/普通两种模式下命令相同，仅超时不同）
            cmd = [soffice_path, "--headless", "--convert-to", "pdf", "--outdir", output_dir, file_path]

            logger.info(f"执行文档转换: {file_path}")
            result = self._convert_with_fallback(cmd, use_listener=use_listener, timeout=timeout)
            if result is None:
                return None
            if result.returncode != 0:
                logger.error(f"文档转换失败: {result.stderr}")
                return None

            # 查找生成的 PDF 文件
            base_name = Path(file_path).stem
            expected_pdf = os.path.join(output_dir, f"{base_name}.pdf")

            if os.path.exists(expected_pdf):
                logger.info(f"文档转换成功: {expected_pdf}")
                return expected_pdf
            else:
                # LibreOffice 可能使用了不同的命名
                pdf_files = [f for f in os.listdir(output_dir) if f.endswith(".pdf")]
                if pdf_files:
                    pdf_path = os.path.join(output_dir, pdf_files[0])
                    logger.info(f"找到转换后的 PDF: {pdf_path}")
                    return pdf_path
                else:
                    logger.error("转换完成但未找到 PDF 文件")
                    return None

        except Exception as e:
            logger.error(f"文档转换异常: {str(e)}")
            logger.exception("详细堆栈:")
            return None

    def batch_convert_to_pdf(self, file_paths: list[str], output_dir: str, timeout: int = 300) -> dict[str, str | None]:
        """
        批量转换 Office 文档为 PDF（单次启动 LibreOffice，传入所有文件路径）

        Args:
            file_paths: Office 文档路径列表
            output_dir: PDF 输出目录
            timeout: 总超时时间（秒）

        Returns:
            {输入文件路径: 输出PDF路径}，失败项值为 None
        """
        from pathlib import Path

        soffice_path = self._find_soffice()
        if not soffice_path:
            logger.error("未找到 LibreOffice，无法批量转换文档")
            return {f: None for f in file_paths}

        os.makedirs(output_dir, exist_ok=True)

        # 单次命令，传入所有文件
        cmd = [soffice_path, "--headless", "--convert-to", "pdf", "--outdir", output_dir] + file_paths

        logger.info(f"批量转换 {len(file_paths)} 个 Office 文档（单次 LibreOffice 命令）")
        logger.debug(f"命令: {' '.join(cmd)}")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if result.returncode != 0:
                logger.error(f"批量转换失败（退出码: {result.returncode}）: {result.stderr}")

            # 验证结果
            results = {}
            for fp in file_paths:
                expected_pdf = os.path.join(output_dir, f"{Path(fp).stem}.pdf")
                results[fp] = expected_pdf if os.path.exists(expected_pdf) else None

            success = sum(1 for v in results.values() if v is not None)
            logger.info(f"批量转换完成: 成功 {success}/{len(file_paths)}")
            return results

        except subprocess.TimeoutExpired:
            logger.error(f"批量转换超时（{timeout}秒），共 {len(file_paths)} 个文件")
            return {f: None for f in file_paths}
        except Exception as e:
            logger.error(f"批量转换异常: {str(e)}")
            return {f: None for f in file_paths}

    def convert_to_modern_format(self, file_path: str, output_dir: str, timeout: int = 60) -> str | None:
        """
        将旧格式 Office 文档转换为新格式
        - .doc -> .docx
        - .ppt -> .pptx
        - .xls -> .xlsx

        Args:
            file_path: Office 文档路径
            output_dir: 输出目录
            timeout: 超时时间（秒）

        Returns:
            转换后的文件路径，失败返回 None
        """
        from pathlib import Path

        soffice_path = self._find_soffice()
        if not soffice_path:
            logger.error("未找到 LibreOffice，无法转换文档格式")
            return None

        # 确定目标格式
        file_ext = Path(file_path).suffix.lower()
        format_map = {".doc": "docx", ".ppt": "pptx", ".xls": "xlsx"}

        if file_ext not in format_map:
            logger.error(f"不支持的文件格式转换: {file_ext}")
            return None

        target_format = format_map[file_ext]
        logger.info(f"开始转换 {file_ext} -> {target_format}: {file_path}")

        # 尝试使用监听进程
        use_listener = self.ensure_listener()
        if use_listener:
            logger.info("使用 LibreOffice 监听进程模式转换文档")
        else:
            logger.warning("LibreOffice 监听进程不可用，使用普通模式（较慢）")

        try:
            # 创建输出目录
            os.makedirs(output_dir, exist_ok=True)

            # 构建转换命令（监听/普通两种模式下命令相同，仅超时不同）
            cmd = [soffice_path, "--headless", "--convert-to", target_format, "--outdir", output_dir, file_path]

            result = self._convert_with_fallback(cmd, use_listener=use_listener, timeout=timeout)
            if result is None:
                return None
            if result.returncode != 0:
                logger.error(f"文档格式转换失败: {result.stderr}")
                return None

            # 查找生成的文件
            base_name = Path(file_path).stem
            expected_file = os.path.join(output_dir, f"{base_name}.{target_format}")

            if os.path.exists(expected_file):
                logger.info(f"文档格式转换成功: {expected_file}")
                return expected_file
            else:
                # LibreOffice 可能使用了不同的命名
                converted_files = [f for f in os.listdir(output_dir) if f.endswith(f".{target_format}")]
                if converted_files:
                    converted_path = os.path.join(output_dir, converted_files[0])
                    logger.info(f"找到转换后的文件: {converted_path}")
                    return converted_path
                else:
                    logger.error("转换完成但未找到输出文件")
                    return None

        except Exception as e:
            logger.error(f"文档格式转换异常: {str(e)}")
            logger.exception("详细堆栈:")
            return None

    def is_listener_running(self) -> bool:
        """检查监听进程是否正在运行"""
        if self._listener_process is None:
            return False
        try:
            return self._listener_process.poll() is None
        except Exception:
            return False


# 全局单例实例
_libreoffice_manager = LibreOfficeManager.get_instance()


def get_libreoffice_manager() -> LibreOfficeManager:
    """获取 LibreOffice 管理器单例"""
    return _libreoffice_manager
