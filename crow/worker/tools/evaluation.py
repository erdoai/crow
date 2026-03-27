"""Evaluation tool: evaluate_run."""

import json

import anthropic
import httpx

from crow.worker.tools import ToolContext, builtin_tool


@builtin_tool(
    name="evaluate_run",
    description=(
        "Evaluate a completed agent run using LLM-as-judge. "
        "Returns a structured evaluation with score (1-5), summary, "
        "strengths, weaknesses, and improvement suggestions. "
        "Use this to assess agent performance before making "
        "improvements."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "job_id": {
                "type": "string",
                "description": "ID of the completed job to evaluate",
            },
            "criteria": {
                "type": "string",
                "description": (
                    "Optional evaluation criteria or rubric. "
                    "If omitted, uses general quality assessment."
                ),
            },
        },
        "required": ["job_id"],
    },
)
async def _handle_evaluate_run(inp: dict, ctx: ToolContext) -> str:
    eval_job_id = inp["job_id"]
    criteria = inp.get("criteria", "")

    # Fetch job + conversation messages
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{ctx.server_url}/jobs/{eval_job_id}/evaluation-data",
            headers=ctx.headers,
            timeout=30,
        )
        if resp.status_code != 200:
            return json.dumps(
                {"error": f"Job {eval_job_id} not found"}
            )
        eval_data = resp.json()

    eval_job = eval_data["job"]
    eval_messages = eval_data["messages"]

    if eval_job.get("status") != "completed":
        return json.dumps({
            "error": (
                f"Job status is '{eval_job.get('status')}',"
                " not 'completed'"
            )
        })

    # Build conversation transcript
    conversation_text = "\n".join(
        f"[{m['role']}] {m['content']}" for m in eval_messages
    )

    eval_system = (
        "You are an expert evaluator of AI agent runs. "
        "Analyze the agent's performance and return ONLY valid JSON:\n"
        "{\n"
        '  "score": <integer 1-5, 1=poor 3=adequate 5=excellent>,\n'
        '  "summary": "<one paragraph assessment>",\n'
        '  "strengths": ["<strength>", ...],\n'
        '  "weaknesses": ["<weakness>", ...],\n'
        '  "suggestions": ["<actionable improvement>", ...]\n'
        "}"
    )

    criteria_section = (
        f"\n\nEvaluation criteria: {criteria}" if criteria else ""
    )

    eval_user_msg = (
        f"Evaluate this agent run:\n\n"
        f"Agent: {eval_job.get('agent_name', 'unknown')}\n"
        f"Task input: {eval_job.get('input', '')}\n"
        f"Final output: {eval_job.get('output', '')}\n"
        f"Tokens used: {eval_job.get('tokens_used', 'unknown')}\n\n"
        f"Conversation ({len(eval_messages)} messages):\n"
        f"{conversation_text}"
        f"{criteria_section}"
    )

    # Call Claude as judge
    if not ctx.settings or not ctx.settings.anthropic_api_key:
        return json.dumps(
            {"error": "No Anthropic API key configured"}
        )

    ai_client = anthropic.AsyncAnthropic(
        api_key=ctx.settings.anthropic_api_key,
    )
    response = await ai_client.messages.create(
        model=ctx.settings.anthropic_model,
        max_tokens=1024,
        system=eval_system,
        messages=[{"role": "user", "content": eval_user_msg}],
    )

    result_text = response.content[0].text
    try:
        evaluation = json.loads(result_text)
    except json.JSONDecodeError:
        evaluation = {"raw": result_text, "parse_error": True}

    evaluation["job_id"] = eval_job_id
    evaluation["agent_name"] = eval_job.get("agent_name")
    evaluation["tokens_used_by_evaluation"] = (
        response.usage.input_tokens + response.usage.output_tokens
    )

    return json.dumps(evaluation, indent=2)
