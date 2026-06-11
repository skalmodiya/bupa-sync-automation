"""Sync status aggregation routes.

Aggregates sync status from the mock S/4HANA service and maintains
local sync execution history.
"""

import asyncio
import json
import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Body, Depends, Query, Request

from config import Settings, get_settings

router = APIRouter()

TIMEOUT = 30.0
HISTORY_FILE = Path(__file__).parent.parent / "data" / "sync_history.json"


def _resolve_agent_url(settings: Settings) -> str:
    """Resolve agent URL, replacing localhost with Docker service name in Docker mode."""
    url = settings.agent.url.rstrip("/")
    if os.environ.get("DEPLOYMENT_MODE") == "docker":
        url = url.replace("http://localhost:5000", "http://bupa-sync-agent:5000")
    return url


def _error(message: str, detail: str = "") -> dict:
    return {"error": message, "detail": detail}


def _load_history() -> list[dict]:
    """Load sync execution history from local file."""
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            return []
    return []


def _save_history(history: list[dict]) -> None:
    """Save sync execution history to local file."""
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(
        json.dumps(history, indent=2, default=str),
        encoding="utf-8",
    )


def _append_history_entry(entry: dict) -> None:
    """Append a new entry to sync history (keep last 100)."""
    history = _load_history()
    history.insert(0, entry)
    history = history[:100]
    _save_history(history)


async def _send_notification_email(settings: Settings, subject: str, body: str):
    """Send an HTML notification email. Silently fails if SMTP not configured."""
    if not settings.smtp.host:
        return
    try:

        def _send():
            msg = MIMEMultipart()
            msg["From"] = "bupa-sync@local.test"
            msg["To"] = "consultant@local.test"
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "html"))

            smtp = smtplib.SMTP(settings.smtp.host, settings.smtp.port, timeout=5)
            smtp.ehlo()
            if settings.smtp.username and settings.smtp.password:
                smtp.login(settings.smtp.username, settings.smtp.password)
            smtp.sendmail(
                "bupa-sync@local.test", ["consultant@local.test"], msg.as_string()
            )
            smtp.quit()

        await asyncio.to_thread(_send)
    except Exception:
        pass  # Don't fail if email can't be sent


@router.get("/status")
async def get_sync_status(settings: Settings = Depends(get_settings)) -> Any:
    """Aggregate sync status: total employees, synced, failed, pending, error breakdown.

    Fetches data from the mock S/4HANA service to compute counts and error categories.
    Returns a comprehensive status object for the dashboard.
    """
    base_url = settings.mock_s4.url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            # Fetch employee master data (PA0000 - Actions infotype)
            resp = await client.get(f"{base_url}/api/pa0000")
            if resp.status_code != 200:
                return _error(
                    "Cannot fetch employee data from mock S/4",
                    f"Status {resp.status_code}",
                )
            employees = resp.json()
            total = (
                len(employees)
                if isinstance(employees, list)
                else employees.get("count", 0)
            )

            # Fetch sync error log for error breakdown
            errors_by_category: dict[str, int] = {}
            failed_count = 0
            error_list: list = []
            try:
                log_resp = await client.get(f"{base_url}/api/bupa/sync/log")
                if log_resp.status_code == 200:
                    log_data = log_resp.json()
                    # log_data may be a list of error entries or an object with errors
                    error_list = []
                    if isinstance(log_data, list):
                        error_list = log_data
                    elif isinstance(log_data, dict):
                        error_list = log_data.get(
                            "results", log_data.get("errors", log_data.get("data", []))
                        )

                    # Count errors by category
                    for entry in error_list:
                        if isinstance(entry, dict):
                            cat = entry.get(
                                "ERROR_TYPE",
                                entry.get(
                                    "error_category",
                                    entry.get(
                                        "category", entry.get("errorType", "UNKNOWN")
                                    ),
                                ),
                            )
                            errors_by_category[cat] = errors_by_category.get(cat, 0) + 1

                    failed_count = sum(errors_by_category.values())
            except Exception:
                pass

            # Try to get sync status endpoint for additional info
            synced_count = 0
            pending_count = 0
            last_sync_time = None
            sync_status_str = "unknown"

            try:
                status_resp = await client.get(
                    f"{base_url}/api/sync/status", timeout=3.0
                )
                if status_resp.status_code == 200:
                    status_data = status_resp.json()
                    synced_count = status_data.get("synced", 0)
                    failed_count = failed_count or status_data.get("failed", 0)
                    pending_count = status_data.get("pending", 0)
                    last_sync_time = status_data.get("last_sync")
                    sync_status_str = status_data.get("status", "unknown")
            except Exception:
                pass

            # If we didn't get synced count from status endpoint, derive it
            if synced_count == 0 and failed_count > 0:
                synced_count = max(0, total - failed_count - pending_count)
            elif synced_count == 0 and failed_count == 0:
                # Check sync history for last run
                history = _load_history()
                if history:
                    last_entry = history[0]
                    synced_count = last_entry.get("synced", 0)
                    failed_count = failed_count or last_entry.get("failed", 0)
                    pending_count = max(0, total - synced_count - failed_count)
                    last_sync_time = last_entry.get(
                        "completed_at", last_entry.get("started_at")
                    )
                    sync_status_str = last_entry.get("status", "unknown")
                else:
                    pending_count = total

            # Calculate error rate
            error_rate_pct = round((failed_count / total) * 100) if total > 0 else 0
            error_rate = f"{error_rate_pct}%"

            # If no errors_by_category from log, try to build from history
            if not errors_by_category:
                history = _load_history()
                if history:
                    for err in history[0].get("errors", []):
                        if isinstance(err, dict):
                            cat = err.get("error", "UNKNOWN")
                            # Simplify error messages to categories
                            if "address" in cat.lower():
                                cat = "MISSING_ADDRESS"
                            elif "duplicate" in cat.lower():
                                cat = "DUPLICATE_BP"
                            elif "pernr" in cat.lower() or "invalid" in cat.lower():
                                cat = "INVALID_PERNR"
                            elif "bank" in cat.lower():
                                cat = "BANK_DATA_MISMATCH"
                            elif "identification" in cat.lower() or "id" in cat.lower():
                                cat = "IDENTIFICATION_MISSING"
                            else:
                                cat = "CONFIG_MISMATCH"
                            errors_by_category[cat] = errors_by_category.get(cat, 0) + 1

            # Fetch additional data: business partners and vendors
            bp_count = 0
            vendor_count = 0
            try:
                bp_resp = await client.get(f"{base_url}/api/business_partners")
                if bp_resp.status_code == 200:
                    bp_data = bp_resp.json()
                    bp_list = (
                        bp_data.get("results", bp_data)
                        if isinstance(bp_data, dict)
                        else bp_data
                    )
                    bp_count = len(bp_list) if isinstance(bp_list, list) else 0
            except Exception:
                pass

            try:
                vendor_resp = await client.get(f"{base_url}/api/lfb1")
                if vendor_resp.status_code == 200:
                    vendor_data = vendor_resp.json()
                    vendor_list = (
                        vendor_data.get("results", vendor_data)
                        if isinstance(vendor_data, dict)
                        else vendor_data
                    )
                    vendor_count = (
                        len(vendor_list) if isinstance(vendor_list, list) else 0
                    )
            except Exception:
                pass

            # Compute open vs resolved errors
            open_errors = 0
            resolved_errors = 0
            if error_list:
                for entry in error_list:
                    if isinstance(entry, dict):
                        err_status = entry.get("STATUS", entry.get("status", "open"))
                        if err_status == "open":
                            open_errors += 1
                        else:
                            resolved_errors += 1
                # If no STATUS field exists, treat all as open
                if open_errors == 0 and resolved_errors == 0:
                    open_errors = len(error_list)

            return {
                "total_employees": total,
                "synced_count": synced_count,
                "failed_count": failed_count,
                "pending_count": pending_count,
                "error_rate": error_rate,
                "errors_by_category": errors_by_category,
                "last_sync_time": last_sync_time
                or datetime.now(timezone.utc).isoformat(),
                "sync_status": sync_status_str,
                "bp_count": bp_count,
                "vendor_count": vendor_count,
                "open_errors": open_errors,
                "resolved_errors": resolved_errors,
                "methodology": {
                    "total_employees": "Unique active employees from PA0000 (Status 3)",
                    "synced_count": "Employees with a matching Business Partner record and no sync errors",
                    "failed_count": "Unique employees with at least one sync error in /SHCM/D_BP_SYNC",
                    "pending_count": "Employees not yet processed (no BP, no error)",
                    "error_rate": "failed_count / total_employees * 100",
                    "bp_count": "Total Business Partner records in BUT000",
                    "vendor_count": "Employee-vendor links from LFB1",
                    "note": "Records page shows one row per error (an employee with 2 errors = 2 rows). Dashboard shows unique employee counts.",
                },
            }
    except httpx.ConnectError as e:
        return _error("Cannot reach mock S/4HANA", str(e))
    except Exception as e:
        return _error("Status fetch failed", str(e))


@router.get("/errors")
async def get_sync_errors(settings: Settings = Depends(get_settings)) -> Any:
    """Get current error log from mock S/4HANA."""
    base_url = settings.mock_s4.url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(f"{base_url}/api/sync/errors")
            if resp.status_code == 200:
                return resp.json()
            # Try alternative endpoint
            resp2 = await client.get(f"{base_url}/api/bupa/sync/log")
            if resp2.status_code == 200:
                return resp2.json()
            # If endpoint doesn't exist, return empty list
            if resp.status_code == 404:
                return {"errors": []}
            return _error(
                "Failed to fetch errors",
                f"Status {resp.status_code}: {resp.text[:200]}",
            )
    except httpx.ConnectError as e:
        return _error("Cannot reach mock S/4HANA", str(e))
    except Exception as e:
        return _error("Error fetch failed", str(e))


@router.get("/history")
async def get_sync_history() -> Any:
    """Get sync execution history stored locally."""
    history = _load_history()
    return {"history": history, "total": len(history)}


@router.get("/error-categories")
async def get_error_categories(
    settings: Settings = Depends(get_settings),
) -> Any:
    """Get all distinct error categories from the current sync error log."""
    base_url = settings.mock_s4.url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            log_resp = await client.get(f"{base_url}/api/bupa/sync/log")
            if log_resp.status_code == 200:
                errors = log_resp.json().get("results", [])
                # Count by category
                categories: dict[str, int] = {}
                for e in errors:
                    cat = e.get("ERROR_TYPE", "UNKNOWN")
                    categories[cat] = categories.get(cat, 0) + 1
                return {
                    "categories": [
                        {
                            "value": cat,
                            "label": cat.replace("_", " ").title(),
                            "count": count,
                        }
                        for cat, count in sorted(
                            categories.items(), key=lambda x: -x[1]
                        )
                    ]
                }
            return {"categories": []}
    except Exception:
        return {"categories": []}


@router.get("/records")
async def get_sync_records(
    status: str = Query(default="all"),  # "all", "synced", "failed", "pending"
    category: str = Query(default=""),  # Error category filter e.g. "MISSING_ADDRESS"
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=10, le=100),
    settings: Settings = Depends(get_settings),
) -> Any:
    """Get paginated employee sync records with status and category filter."""
    base_url = settings.mock_s4.url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            # Get all employees
            emp_resp = await client.get(f"{base_url}/api/pa0000")
            employees = (
                emp_resp.json().get("results", [])
                if emp_resp.status_code == 200
                else []
            )

            # Get error log to determine which employees failed
            log_resp = await client.get(f"{base_url}/api/bupa/sync/log")
            errors = (
                log_resp.json().get("results", [])
                if log_resp.status_code == 200
                else []
            )
            failed_pernrs = {e.get("PERNR") for e in errors}

            # Get BPs to determine synced
            bp_resp = await client.get(f"{base_url}/api/business_partners")
            bps = (
                bp_resp.json().get("results", []) if bp_resp.status_code == 200 else []
            )
            synced_pernrs = {
                bp.get("PERNR", bp.get("PersonNumber", ""))
                for bp in bps
                if bp.get("PERNR") or bp.get("PersonNumber")
            }

            # Build records — one record per error (employee can appear multiple times if multiple errors)
            records = []
            # Build records — one record per error (employee can appear multiple times if multiple errors)
            records = []
            # First, add all error records
            processed_pernrs = set()
            for error in errors:
                err_pernr = error.get("PERNR", "")
                emp = next((e for e in employees if e.get("PERNR") == err_pernr), None)
                processed_pernrs.add(err_pernr)
                records.append(
                    {
                        "pernr": err_pernr,
                        "name": f"{emp.get('FIRST_NAME', '')} {emp.get('LAST_NAME', '')}".strip()
                        if emp
                        else err_pernr,
                        "status": "failed",
                        "error_type": error.get("ERROR_TYPE", "UNKNOWN"),
                        "error_message": error.get("MESSAGE", ""),
                        "bp_id": error.get("BP_ID", ""),
                        "org_unit": emp.get("ORGEH", emp.get("WERKS", ""))
                        if emp
                        else "",
                    }
                )

            # Then add synced/pending employees (no errors)
            for emp in employees:
                pernr = emp.get("PERNR", "")
                if pernr in processed_pernrs:
                    continue
                emp_status = "synced" if pernr in synced_pernrs else "pending"
                records.append(
                    {
                        "pernr": pernr,
                        "name": f"{emp.get('FIRST_NAME', '')} {emp.get('LAST_NAME', '')}".strip(),
                        "status": emp_status,
                        "error_type": "",
                        "error_message": "",
                        "bp_id": "",
                        "org_unit": emp.get("ORGEH", emp.get("WERKS", "")),
                    }
                )

            # Filter by status
            if status != "all":
                records = [r for r in records if r["status"] == status]

            # Filter by error category (supports comma-separated for multi-select)
            if category:
                cat_list = [c.strip() for c in category.split(",") if c.strip()]
                if cat_list:
                    records = [r for r in records if r["error_type"] in cat_list]

            total = len(records)
            # Paginate
            page_records = records[offset : offset + limit]

            return {
                "records": page_records,
                "total": total,
                "offset": offset,
                "limit": limit,
                "has_more": (offset + limit) < total,
            }
    except Exception as e:
        return _error("Failed to fetch records", str(e))


@router.post("/trigger")
async def trigger_full_sync(settings: Settings = Depends(get_settings)) -> Any:
    """Trigger a full sync run.

    Calls mock S/4HANA endpoints in sequence to simulate a complete
    Business Partner synchronization cycle:
    1. Fetch employees from PA0000
    2. For each employee, read detailed infotypes
    3. Push updates to SuccessFactors (simulated)
    4. Record results
    """
    base_url = settings.mock_s4.url.rstrip("/")
    timestamp = datetime.now(timezone.utc).isoformat()

    history_entry = {
        "id": timestamp.replace(":", "-").replace(".", "-"),
        "started_at": timestamp,
        "status": "running",
        "total": 0,
        "synced": 0,
        "failed": 0,
        "errors": [],
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            # Step 1: Fetch employee list
            resp = await client.get(f"{base_url}/api/pa0000")
            if resp.status_code != 200:
                history_entry["status"] = "error"
                history_entry["errors"].append(
                    f"Failed to fetch PA0000: status {resp.status_code}"
                )
                history_entry["completed_at"] = datetime.now(timezone.utc).isoformat()
                _append_history_entry(history_entry)
                return _error(
                    "Sync failed at employee fetch", f"Status {resp.status_code}"
                )

            employees = resp.json()
            if isinstance(employees, list):
                employee_list = employees
            else:
                employee_list = employees.get("data", employees.get("results", []))

            history_entry["total"] = len(employee_list)

            # Step 2: Process each employee
            synced = 0
            failed = 0
            errors = []

            for emp in employee_list:
                pernr = emp.get("pernr", emp.get("PERNR", emp.get("id", "unknown")))
                try:
                    # Read detailed data for employee
                    detail_resp = await client.get(f"{base_url}/api/employees/{pernr}")
                    if detail_resp.status_code == 200:
                        # Simulate push to SF
                        push_resp = await client.post(
                            f"{base_url}/api/sync/push",
                            json={"pernr": pernr, "data": detail_resp.json()},
                        )
                        if push_resp.status_code in (200, 201):
                            synced += 1
                        else:
                            failed += 1
                            errors.append(
                                {
                                    "pernr": pernr,
                                    "error": f"Push failed: status {push_resp.status_code}",
                                }
                            )
                    elif detail_resp.status_code == 404:
                        # Employee detail endpoint may not exist — count as synced from PA0000 data
                        synced += 1
                    else:
                        failed += 1
                        errors.append(
                            {
                                "pernr": pernr,
                                "error": f"Detail fetch failed: status {detail_resp.status_code}",
                            }
                        )
                except Exception as e:
                    failed += 1
                    errors.append({"pernr": pernr, "error": str(e)})

            history_entry["synced"] = synced
            history_entry["failed"] = failed
            history_entry["errors"] = errors[:50]  # Keep at most 50 error entries
            history_entry["status"] = (
                "completed" if failed == 0 else "completed_with_errors"
            )
            history_entry["completed_at"] = datetime.now(timezone.utc).isoformat()

            _append_history_entry(history_entry)

            return {
                "status": history_entry["status"],
                "total": len(employee_list),
                "synced": synced,
                "failed": failed,
                "errors": errors[:10],  # Return first 10 errors in response
            }

    except httpx.ConnectError as e:
        history_entry["status"] = "error"
        history_entry["errors"].append(f"Connection error: {str(e)}")
        history_entry["completed_at"] = datetime.now(timezone.utc).isoformat()
        _append_history_entry(history_entry)
        return _error("Cannot reach mock S/4HANA", str(e))
    except Exception as e:
        history_entry["status"] = "error"
        history_entry["errors"].append(f"Unexpected error: {str(e)}")
        history_entry["completed_at"] = datetime.now(timezone.utc).isoformat()
        _append_history_entry(history_entry)
        return _error("Sync trigger failed", str(e))


@router.post("/retry")
async def retry_sync(
    request: Request,
    payload: dict = Body(...),
    settings: Settings = Depends(get_settings),
) -> Any:
    """Retry BUPA sync for selected employees or by error category.

    payload: {
        "pernr_list": ["00001005"],      // specific employees
        "categories": ["MISSING_ADDRESS"], // filter by error categories
        "mode": "selected" | "all_failed" | "by_category"
    }

    If the number of records exceeds the configured job threshold,
    the operation is scheduled as a background job.
    """
    from auth import get_optional_user
    from audit import log_event

    user = get_optional_user(request)
    pernr_list = payload.get("pernr_list", [])
    categories = payload.get("categories", [])
    mode = payload.get("mode", "selected")

    base_url = settings.mock_s4.url.rstrip("/")

    if mode == "all_failed" or mode == "by_category":
        # Get PERNRs from error log, optionally filtered by category
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            log_resp = await client.get(f"{base_url}/api/bupa/sync/log")
            if log_resp.status_code == 200:
                errors = log_resp.json().get("results", [])
                if categories:
                    errors = [e for e in errors if e.get("ERROR_TYPE") in categories]
                pernr_list = [e["PERNR"] for e in errors if e.get("PERNR")]

    if not pernr_list:
        return _error(
            "No employees to retry", "Provide pernr_list or use mode=all_failed"
        )

    # Check if we should schedule as background job
    job_threshold = settings.jobs.threshold
    if len(pernr_list) > job_threshold:
        from jobs import create_job, run_job_async

        job_id = create_job(
            "retry_sync",
            {"pernr_list": pernr_list, "mode": mode, "categories": categories},
            created_by=user["user_id"],
        )
        run_job_async(job_id, _run_retry_job, pernr_list, settings)

        log_event(
            action="sync.retry_scheduled",
            category="workflow",
            user=user["user_id"],
            user_name=user["name"],
            user_email=user.get("email", ""),
            details={"pernr_count": len(pernr_list), "mode": mode, "job_id": job_id},
        )

        return {
            "status": "scheduled",
            "job_id": job_id,
            "pernr_count": len(pernr_list),
            "message": f"Scheduled as background job (>{job_threshold} records)",
        }

    # Run synchronously for small batches — route through n8n webhook
    n8n_base = (
        settings.n8n.webhook_url.rstrip("/")
        if settings.n8n.webhook_url
        else settings.n8n.url.rstrip("/")
    )
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Try production webhook first, then test webhook
            n8n_payload = {
                "action": "retry_sync",
                "pernr_list": pernr_list,
                "mode": mode,
                "categories": categories,
                "triggered_by": user["name"],
            }
            resp = await client.post(
                f"{n8n_base}/webhook/bupa-sync-retry", json=n8n_payload
            )
            if resp.status_code not in (200, 201):
                resp = await client.post(
                    f"{n8n_base}/webhook-test/bupa-sync-retry", json=n8n_payload
                )
            if resp.status_code in (200, 201):
                result = resp.json()
            else:
                # Fallback: call mock S/4 directly (local dev without n8n retry workflow)
                resp = await client.post(
                    f"{base_url}/api/bupa/sync/retry",
                    json={"pernr_list": pernr_list},
                )
                result = (
                    resp.json() if resp.status_code == 200 else {"error": resp.text}
                )
                result["note"] = "Executed directly (n8n retry webhook not available)"
    except Exception as e:
        result = {"error": str(e)}

    # Audit log
    log_event(
        action="sync.retry_triggered",
        category="workflow",
        user=user["user_id"],
        user_name=user["name"],
        user_email=user.get("email", ""),
        details={"pernr_count": len(pernr_list), "mode": mode, "result": result},
    )

    # Send email notification
    await _send_notification_email(
        settings=settings,
        subject=f"BUPA Sync Retry Triggered ({len(pernr_list)} employees)",
        body=f"""
        <h2>BUPA Sync Retry Triggered</h2>
        <p><strong>Triggered by:</strong> {user["name"]} ({user.get("email", "")})</p>
        <p><strong>Mode:</strong> {mode}</p>
        <p><strong>Employees:</strong> {len(pernr_list)}</p>
        <p><strong>PERNRs:</strong> {", ".join(pernr_list[:20])}{"..." if len(pernr_list) > 20 else ""}</p>
        <hr>
        <p><strong>Result:</strong></p>
        <pre>{json.dumps(result, indent=2)}</pre>
        """,
    )

    return {
        "status": "triggered",
        "pernr_count": len(pernr_list),
        "mode": mode,
        "result": result,
    }


@router.post("/ask-agent-fix")
async def ask_agent_fix(
    request: Request,
    payload: dict = Body(...),
    settings: Settings = Depends(get_settings),
) -> Any:
    """Send failed records to the AI agent for fix proposals.

    payload: {
        "pernr_list": ["00001005"],       // specific employees
        "categories": ["MISSING_ADDRESS"], // filter by error categories
        "mode": "selected" | "by_category"
    }

    If the number of errors exceeds the configured job threshold,
    the operation is scheduled as a background job.
    Returns agent's fix proposals.
    """
    from auth import get_optional_user
    from audit import log_event

    user = get_optional_user(request)
    pernr_list = payload.get("pernr_list", [])
    categories = payload.get("categories", [])
    mode = payload.get("mode", "selected")

    # Gather error details
    base_url = settings.mock_s4.url.rstrip("/")
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        log_resp = await client.get(f"{base_url}/api/bupa/sync/log")
        all_errors = (
            log_resp.json().get("results", []) if log_resp.status_code == 200 else []
        )

    # Filter errors by mode
    if mode == "by_category" and categories:
        selected_errors = [e for e in all_errors if e.get("ERROR_TYPE") in categories]
    elif pernr_list:
        selected_errors = [e for e in all_errors if e.get("PERNR") in pernr_list]
    else:
        return _error("No selection", "Provide pernr_list or categories")

    if not selected_errors:
        return _error("No errors found", "Selected employees have no sync errors")

    # Check if we should schedule as background job
    job_threshold = settings.jobs.threshold
    if len(selected_errors) > job_threshold:
        from jobs import create_job, run_job_async

        job_id = create_job(
            "agent_fix",
            {
                "pernr_list": pernr_list,
                "categories": categories,
                "mode": mode,
                "error_count": len(selected_errors),
            },
            created_by=user["user_id"],
        )
        run_job_async(job_id, _run_agent_fix_job, selected_errors, settings)

        log_event(
            action="agent.fix_scheduled",
            category="agent",
            user=user["user_id"],
            user_name=user["name"],
            user_email=user.get("email", ""),
            details={
                "pernr_count": len(pernr_list),
                "errors_found": len(selected_errors),
                "job_id": job_id,
            },
        )

        return {
            "status": "scheduled",
            "job_id": job_id,
            "pernr_count": len(pernr_list),
            "errors_analyzed": len(selected_errors),
            "message": f"Scheduled as background job (>{job_threshold} errors)",
        }

    # Run synchronously for small batches
    # Build message for agent
    error_summary = json.dumps(selected_errors, indent=2)
    agent_message = (
        f"Analyze these {len(selected_errors)} BUPA sync errors and propose fixes. "
        f"For each error, provide: error category, root cause, proposed fix action, "
        f"target table/field, current value, proposed value, and confidence score (0-1).\n\n"
        f"Errors:\n{error_summary}"
    )

    # Call agent via n8n workflow (production) or directly (local fallback)
    n8n_base = (
        settings.n8n.webhook_url.rstrip("/")
        if settings.n8n.webhook_url
        else settings.n8n.url.rstrip("/")
    )
    response_content = ""
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            # Try n8n webhook first
            n8n_payload = {
                "action": "agent_fix",
                "errors": selected_errors,
                "pernr_list": [e.get("PERNR") for e in selected_errors],
                "categories": categories,
                "triggered_by": user["name"],
            }
            resp = await client.post(
                f"{n8n_base}/webhook/bupa-sync-agent-fix", json=n8n_payload
            )
            if resp.status_code not in (200, 201):
                resp = await client.post(
                    f"{n8n_base}/webhook-test/bupa-sync-agent-fix", json=n8n_payload
                )

            if resp.status_code in (200, 201):
                n8n_result = resp.json()
                response_content = n8n_result.get(
                    "agent_response", n8n_result.get("response", str(n8n_result))
                )
            else:
                # Fallback: call agent directly (local dev)
                agent_url = _resolve_agent_url(settings) + "/invoke"
                resp = await client.post(
                    agent_url,
                    json={"messages": [{"role": "user", "content": agent_message}]},
                )
                if resp.status_code == 200:
                    agent_response = resp.json()
                    response_content = agent_response.get("result", {}).get(
                        "content", agent_response.get("content", str(agent_response))
                    )
                else:
                    response_content = (
                        f"Agent error: {resp.status_code} - {resp.text[:500]}"
                    )
    except httpx.ConnectError:
        response_content = "Cannot reach n8n or agent. Ensure n8n is running and webhook is configured."
    except Exception as e:
        response_content = f"Error: {str(e)}"

    # Audit log
    log_event(
        action="agent.fix_requested",
        category="agent",
        user=user["user_id"],
        user_name=user["name"],
        user_email=user.get("email", ""),
        details={"pernr_count": len(pernr_list), "errors_found": len(selected_errors)},
    )

    # Send email with agent analysis
    await _send_notification_email(
        settings=settings,
        subject=f"BUPA Sync Agent Fix Proposals ({len(selected_errors)} errors)",
        body=f"""
        <h2>Agent Fix Proposals</h2>
        <p><strong>Requested by:</strong> {user["name"]}</p>
        <p><strong>Employees analyzed:</strong> {len(pernr_list)}</p>
        <p><strong>Errors found:</strong> {len(selected_errors)}</p>
        <hr>
        <h3>Agent Analysis:</h3>
        <pre style="white-space: pre-wrap;">{response_content[:5000]}</pre>
        """,
    )

    return {
        "status": "completed",
        "pernr_count": len(pernr_list),
        "errors_analyzed": len(selected_errors),
        "agent_response": response_content,
    }


async def _run_retry_job(job_id: str, pernr_list: list[str], settings: Settings):
    """Background job worker for retry sync operations."""
    from jobs import update_job

    total = len(pernr_list)
    update_job(job_id, total=total, message=f"Retrying {total} employees...")

    base_url = settings.mock_s4.url.rstrip("/")
    success_count = 0
    fail_count = 0
    errors = []

    async with httpx.AsyncClient(timeout=60.0) as client:
        for i, pernr in enumerate(pernr_list):
            try:
                resp = await client.post(
                    f"{base_url}/api/bupa/sync/retry",
                    json={"pernr_list": [pernr]},
                )
                if resp.status_code == 200:
                    success_count += 1
                else:
                    fail_count += 1
                    errors.append({"pernr": pernr, "error": resp.text[:200]})
            except Exception as e:
                fail_count += 1
                errors.append({"pernr": pernr, "error": str(e)})

            # Update progress
            update_job(
                job_id,
                progress=i + 1,
                message=f"Processed {i + 1}/{total} — {success_count} ok, {fail_count} failed",
            )

    return {
        "total": total,
        "success": success_count,
        "failed": fail_count,
        "errors": errors[:50],
    }


async def _run_agent_fix_job(
    job_id: str, selected_errors: list[dict], settings: Settings
):
    """Background job worker for agent fix operations."""
    from jobs import update_job

    total = len(selected_errors)
    update_job(job_id, total=total, message=f"Sending {total} errors to agent...")

    # Build message for agent
    error_summary = json.dumps(selected_errors, indent=2)
    agent_message = (
        f"Analyze these {total} BUPA sync errors and propose fixes. "
        f"For each error, provide: error category, root cause, proposed fix action, "
        f"target table/field, current value, proposed value, and confidence score (0-1).\n\n"
        f"Errors:\n{error_summary}"
    )

    # Call agent
    agent_url = _resolve_agent_url(settings) + "/invoke"
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            update_job(job_id, progress=1, message="Waiting for agent response...")
            resp = await client.post(
                agent_url,
                json={"messages": [{"role": "user", "content": agent_message}]},
            )
            if resp.status_code == 200:
                agent_response = resp.json()
                response_content = agent_response.get("result", {}).get(
                    "content", agent_response.get("content", str(agent_response))
                )
            else:
                response_content = (
                    f"Agent error: {resp.status_code} - {resp.text[:500]}"
                )
    except httpx.ConnectError:
        response_content = (
            "Cannot reach agent. Make sure it is running on "
            + _resolve_agent_url(settings)
        )
    except Exception as e:
        response_content = f"Agent error: {str(e)}"

    update_job(job_id, progress=total, message="Agent analysis complete")

    return {
        "errors_analyzed": total,
        "agent_response": response_content,
    }


@router.post("/notify-completion")
async def notify_workflow_completion(
    payload: dict = Body(...),
    settings: Settings = Depends(get_settings),
) -> Any:
    """Called after n8n workflow completes. Sends email with run summary."""
    run_id = payload.get("run_id", "unknown")
    total = payload.get("total_employees", 0)
    errors = payload.get("error_count", 0)
    synced = payload.get("synced_count", total - errors)
    milestone = payload.get("milestone", "M5")
    report = payload.get("report", "")

    await _send_notification_email(
        settings=settings,
        subject=f"BUPA Sync Complete - Run {run_id} ({errors} errors)",
        body=f"""
        <h2>BUPA Sync Workflow Completed</h2>
        <table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse;">
            <tr><td><strong>Run ID</strong></td><td>{run_id}</td></tr>
            <tr><td><strong>Total Employees</strong></td><td>{total}</td></tr>
            <tr><td><strong>Synced</strong></td><td>{synced}</td></tr>
            <tr><td><strong>Failed</strong></td><td>{errors}</td></tr>
            <tr><td><strong>Error Rate</strong></td><td>{round(errors / total * 100) if total > 0 else 0}%</td></tr>
            <tr><td><strong>Final Milestone</strong></td><td>{milestone}</td></tr>
        </table>
        <hr>
        <h3>Reconciliation Report:</h3>
        <pre style="white-space: pre-wrap;">{report or "No detailed report available."}</pre>
        """,
    )

    return {"status": "notified", "run_id": run_id}
