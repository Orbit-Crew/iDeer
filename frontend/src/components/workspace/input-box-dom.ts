// DOM/editing utilities for the composer's editable surfaces (textarea and
// the inline skill contenteditable). Pure DOM helpers — no React state.

/** Move the caret to the end of a contenteditable element and focus it. */
export function focusContentEditableEnd(element: HTMLElement | null) {
  if (!element) {
    return;
  }

  element.focus();
  const selection = window.getSelection();
  if (!selection) {
    return;
  }

  const range = document.createRange();
  range.selectNodeContents(element);
  range.collapse(false);
  selection.removeAllRanges();
  selection.addRange(range);
}

/**
 * Insert plain text at the current selection when it lives inside `container`.
 * Returns false when the selection is elsewhere, so callers keep their own
 * fallback behavior.
 */
export function insertPlainTextAtSelection(
  container: HTMLElement,
  text: string,
) {
  const selection = window.getSelection();
  if (!selection || selection.rangeCount === 0) {
    return false;
  }

  const range = selection.getRangeAt(0);
  const ancestor = range.commonAncestorContainer;
  if (ancestor !== container && !container.contains(ancestor)) {
    return false;
  }

  range.deleteContents();
  const node = document.createTextNode(text);
  range.insertNode(node);
  range.setStartAfter(node);
  range.setEndAfter(node);
  selection.removeAllRanges();
  selection.addRange(range);
  return true;
}

/**
 * Focus the composer textarea and pre-select the `[...]` placeholder of a
 * suggestion template so the user can jump straight to filling it in.
 */
export function highlightPlaceholder(text: string, root: HTMLElement | null) {
  if (!root) return;
  const textarea = root.querySelector<HTMLTextAreaElement>("textarea");
  if (!textarea) return;
  const selEnd = text.lastIndexOf("]");
  if (selEnd === -1) return;
  const selStart = text.lastIndexOf("[", selEnd);
  if (selStart === -1 || selStart > selEnd) return;
  textarea.setSelectionRange(selStart, selEnd + 1);
  textarea.focus();
}
