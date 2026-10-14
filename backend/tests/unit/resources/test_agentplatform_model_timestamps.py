"""Legacy agentplatform tables must not generate naive UTC timestamps.

``datetime.utcnow`` is deprecated on Python 3.12 and produces naive
datetimes, which the same database mixes with the UTC-aware ``_now()`` used
by the canonical resource tables (report 02-L2).
"""

import app.agentplatform.audit_model  # noqa: F401 - register audit tables
import app.agentplatform.rbac_models  # noqa: F401 - register users_ext
from app.agentplatform.resource_models import ResourceMetadata
from app.agentplatform.visibility_models import VisibilityApplication


def test_resource_metadata_timestamp_defaults_are_utc_aware() -> None:
    table = ResourceMetadata.__table__
    for column_name in ("created_at", "updated_at"):
        default = table.columns[column_name].default
        assert default is not None and default.is_callable
        value = default.arg(None)
        assert value.tzinfo is not None, f"ResourceMetadata.{column_name} default produces a naive datetime"


def test_visibility_application_submitted_at_default_is_utc_aware() -> None:
    default = VisibilityApplication.__table__.columns["submitted_at"].default
    assert default is not None and default.is_callable
    value = default.arg(None)
    assert value.tzinfo is not None, "VisibilityApplication.submitted_at default produces a naive datetime"
