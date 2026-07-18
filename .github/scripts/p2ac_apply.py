from pathlib import Path

path = Path('velvet_bot/handlers/reference_comparison.py')
text = path.read_text(encoding='utf-8')

old_import = 'from velvet_bot.core.config import load_settings\n'
new_import = 'from velvet_bot.audit import TelegramAuditLogger\n' + old_import
if text.count(old_import) != 1:
    raise SystemExit('unexpected audit import anchor count')
text = text.replace(old_import, new_import, 1)

old_signature = '''async def handle_reference_comparison(
    message: Message,
    command: CommandObject,
    database: Database,
    bot: Bot,
) -> None:
'''
new_signature = '''async def handle_reference_comparison(
    message: Message,
    command: CommandObject,
    database: Database,
    bot: Bot,
    audit_logger: TelegramAuditLogger | None = None,
) -> None:
'''
if text.count(old_signature) != 1:
    raise SystemExit('unexpected handler signature count')
text = text.replace(old_signature, new_signature, 1)

old_except = '    except ' + 'Exception as error:\n'
new_except = '    except Exception as error:  # p2-approved-boundary: report-reference-comparison-failure\n'
if text.count(old_except) != 1:
    raise SystemExit(f'unexpected broad catch count: {text.count(old_except)}')
text = text.replace(old_except, new_except, 1)

old_report = '''        logger.exception(
            "Reference comparison failed character_id=%s reference_id=%s",
            character.id,
            reference.id,
        )
        await status.edit_text(
'''
new_report = '''        logger.exception(
            "Reference comparison failed character_id=%s reference_id=%s",
            character.id,
            reference.id,
        )
        if audit_logger is not None:
            await audit_logger.error(
                "Ошибка сравнения с референсом",
                error,
                character_id=character.id,
                reference_id=reference.id,
                result_file_id=result_file_id,
                result_file_unique_id=result_unique_id,
                user_id=message.from_user.id if message.from_user else None,
            )
        await status.edit_text(
'''
if text.count(old_report) != 1:
    raise SystemExit('unexpected failure-report anchor count')
text = text.replace(old_report, new_report, 1)

path.write_text(text, encoding='utf-8')
