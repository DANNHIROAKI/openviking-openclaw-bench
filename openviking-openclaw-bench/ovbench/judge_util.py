from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any



SYSTEM_PROMPT = "You are an expert grader that determines if answers to questions match a gold standard answer."


USER_TEMPLATE = """
Your task is to label an answer to a question as CORRECT or WRONG.
You will be given:
1. a question
2. a gold answer
3. a generated answer

The question asks about something one user should know about the other user based on prior conversations.
Be generous with grading.
- If the generated answer clearly refers to the same topic as the gold answer, count it as CORRECT.
- For time questions, if the generated answer refers to the same date or time period as the gold answer, count it as CORRECT even if the formatting differs.

Question: {question}
Gold answer: {gold_answer}
Generated answer: {response}

Respond with JSON only in this form:
{{"is_correct": "CORRECT" or "WRONG", "reasoning": "one short sentence"}}
""".strip()


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)



def _extract_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_RE.search(text)
        if not match:
            raise
        return json.loads(match.group(0))



def load_answers(path: str) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        if path.endswith(".jsonl"):
            return [json.loads(line) for line in f if line.strip()]
        data = json.load(f)
        if isinstance(data, dict):
            if "grades" in data:
                return data["grades"]
            if "results" in data:
                return data["results"]
        if isinstance(data, list):
            return data
        raise RuntimeError(f"unsupported answers format: {path}")


async def grade_one(
    client,
    *,
    model: str,
    question: str,
    gold_answer: str,
    response: str,
    retries: int = 2,
) -> tuple[bool, str, str]:
    last_exc: Exception | None = None
    for _ in range(retries + 1):
        try:
            resp = await client.chat.completions.create(
                model=model,
                temperature=0,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": USER_TEMPLATE.format(
                            question=question,
                            gold_answer=gold_answer,
                            response=response,
                        ),
                    },
                ],
            )
            content = resp.choices[0].message.content or "{}"
            result = _extract_json(content)
            label = str(result.get("is_correct", result.get("label", "WRONG"))).strip().upper()
            reasoning = str(result.get("reasoning", ""))
            return label == "CORRECT", reasoning, content
        except Exception as exc:
            last_exc = exc
    raise RuntimeError(f"judge failed after retries: {last_exc}")


async def grade_answers(
    answers: list[dict[str, Any]],
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str = "gpt-4o-mini",
    max_concurrency: int = 20,
) -> list[dict[str, Any]]:
    from dotenv import load_dotenv
    from openai import AsyncOpenAI

    load_dotenv()
    client = AsyncOpenAI(
        base_url=base_url or os.getenv("OPENAI_BASE_URL"),
        api_key=api_key or os.getenv("OPENAI_API_KEY"),
    )
    semaphore = asyncio.Semaphore(max(1, max_concurrency))

    async def _task(item: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            is_correct, reasoning, raw = await grade_one(
                client,
                model=model,
                question=str(item["question"]),
                gold_answer=str(item["expected"]),
                response=str(item["response"]),
            )
            return {**item, "grade": is_correct, "judge_reasoning": reasoning, "judge_raw": raw}

    tasks = [_task(item) for item in answers]
    return await asyncio.gather(*tasks)
