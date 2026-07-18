from pathlib import Path

path = Path("velvet_bot/handlers/quality_set_ai.py")
text = path.read_text(encoding="utf-8")
prefix = "    except " + "Exception as error:"
callback_log = '        logger.exception(\n            "Set consistency analysis failed set_id=%s job_id=%s",'
command_log = '        logger.exception("Set consistency command failed set_id=%s job_id=%s", set_id, tracker.job_id)'
callback_old = prefix + "\n" + callback_log
callback_new = prefix + "  # p2-approved-boundary: compensate-set-analysis-callback-job\n" + callback_log
command_old = prefix + "\n" + command_log
command_new = prefix + "  # p2-approved-boundary: compensate-set-analysis-command-job\n" + command_log
if callback_old not in text:
    raise SystemExit("callback boundary not found")
if command_old not in text:
    raise SystemExit("command boundary not found")
text = text.replace(callback_old, callback_new, 1)
text = text.replace(command_old, command_new, 1)
path.write_text(text, encoding="utf-8")
