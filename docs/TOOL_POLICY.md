# Tool Policy — Risk Classification & Approval

Every agent tool in Claw-ED declares a `risk_level` attribute that determines whether the tool requires teacher approval before execution.

## Risk Levels

| Level | Approval Required | Examples |
|-------|------------------|----------|
| `read_only` | Never | search, generate_lesson, query_knowledge_graph |
| `write_local` | Yes, unless `CLAWED_AUTO_APPROVE=1` | export_document, ingest_materials, write_file |
| `network_call` | Yes, unless `CLAWED_AUTO_APPROVE=1` | deep_research, drive_ingest |
| `package_install` | **Always** (even with auto-approve) | install_package |
| `external_publish` | **Always** (even with auto-approve) | (future: share_with_students, drive_upload) |

## How It Works

1. The LLM selects a tool to call
2. `ToolRegistry.execute()` checks the tool's `risk_level`
3. If the level requires approval, `_check_approval()` looks for a standing approval in `ApprovalManager`
4. If no approval exists, the tool is **BLOCKED** and returns an error message
5. The LLM must ask the teacher to approve the action

## Standing Approvals

A teacher can pre-approve a tool by creating a standing approval:
- Created via the `request_approval` tool or the web dashboard
- Stored as JSON files in `~/.eduagent/approvals/`
- Each approval records: teacher_id, tool_name, status, created_at

## For Contributors

When adding a new tool:
1. **Always** declare `risk_level` as a class attribute
2. Choose the most restrictive level that makes sense
3. Generation tools (lesson, unit, assessment) are `read_only` — they produce content but don't modify state
4. Tools that write files or modify config are `write_local`
5. Tools that make external API calls are `network_call`
6. Registration will log a WARNING if `risk_level` is missing

## Auto-Approve Mode

Teachers can enable `CLAWED_AUTO_APPROVE=1` to skip approval for `write_local` and `network_call` tools. This is useful for power users who trust Ed's judgment. `package_install` and `external_publish` always require explicit approval regardless of this setting.
