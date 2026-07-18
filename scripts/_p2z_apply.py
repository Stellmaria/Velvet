from pathlib import Path

path = Path("velvet_bot/handlers/quality_operations.py")
text = path.read_text(encoding="utf-8")
old = "    except Exception as error:\n        logger.exception(\"Manual quality analysis failed job_id=%s\", tracker.job_id)\n"
new = "    except Exception as error:  # p2-approved-boundary: compensate-manual-quality-job\n        logger.exception(\"Manual quality analysis failed job_id=%s\", tracker.job_id)\n"
if old not in text:
    raise SystemExit("manual quality boundary not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
