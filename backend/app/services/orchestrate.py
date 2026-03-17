"""watsonx Orchestrate client for the main chat experience."""

import asyncio
from typing import Any, Iterable

import httpx
from ibm_cloud_sdk_core.authenticators import MCSPAuthenticator, MCSPV2Authenticator

from app.config import get_settings


SYSTEM_PROMPT_TEMPLATE = """You are an educational assistant helping a beginner learn about {topic_title}.

You have access to a web search tool. Use it to find information relevant to the user's question about {search_scope}.

Rules you must follow without exception:
1. Search before answering. Do not answer from memory alone.
2. Answer ONLY using information found in your search results.
3. Do NOT generate, guess, or invent any URLs or source links.
   Source links will be attached separately by the system.
4. If the search results do not contain enough information to answer the question, say exactly:
   "I don't have enough information on that right now. Try checking the sources below or rephrasing your question."
5. Keep your answer under 150 words.
6. Use simple, beginner-friendly language. Define technical terms before using them.
7. Stay focused on {topic_title}. If the question is unrelated, say:
   "I'm focused on {topic_title} right now — ask me anything about that!"

User question: {question}"""


async def call_orchestrate(
    topic_title: str,
    search_scope: str,
    question: str,
) -> dict:
    settings = get_settings()

    if (
        (not settings.orchestrate_api_key and not settings.orchestrate_access_token)
        or not settings.orchestrate_agent_id
        or not settings.orchestrate_instance_url
    ):
        return _stub_response(topic_title, question)

    prompt = SYSTEM_PROMPT_TEMPLATE.format(
        topic_title=topic_title,
        search_scope=search_scope,
        question=question,
    )

    base_url = settings.orchestrate_instance_url.rstrip('/')
    token = settings.orchestrate_access_token or _get_mcsp_token(
        api_key=settings.orchestrate_api_key,
        instance_url=base_url,
        iam_url=settings.orchestrate_iam_url,
    )
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }

    async with httpx.AsyncClient(timeout=settings.orchestrate_timeout_seconds) as client:
        run_response = await client.post(
            f'{base_url}/v1/orchestrate/runs',
            headers=headers,
            json={
                'agent_id': settings.orchestrate_agent_id,
                'message': {'role': 'user', 'content': prompt},
            },
        )
        run_response.raise_for_status()
        run_data = run_response.json()

        run_id = run_data.get('run_id')
        thread_id = run_data.get('thread_id')
        if not run_id or not thread_id:
            raise RuntimeError('Orchestrate did not return a run_id and thread_id.')

        await _wait_for_run_completion(client, base_url, headers, run_id)
        messages_response = await client.get(
            f'{base_url}/v1/orchestrate/threads/{thread_id}/messages',
            headers=headers,
        )
        messages_response.raise_for_status()

    answer = _extract_latest_assistant_text(messages_response.json())
    if not answer:
        answer = 'I could not extract a response from watsonx Orchestrate.'
    return {'answer': answer, 'sources': []}


def _get_mcsp_token(*, api_key: str, instance_url: str, iam_url: str) -> str:
    try:
        return MCSPAuthenticator(apikey=api_key, url=iam_url).token_manager.get_token()
    except Exception:
        instance_id = instance_url.rsplit('instances/', 1)[-1]
        return MCSPV2Authenticator(
            apikey=api_key,
            url='https://account-iam.platform.saas.ibm.com',
            scope_collection_type='services',
            scope_id=instance_id,
        ).token_manager.get_token()


async def _wait_for_run_completion(
    client: httpx.AsyncClient,
    base_url: str,
    headers: dict[str, str],
    run_id: str,
    *,
    max_attempts: int = 30,
    delay_seconds: float = 2.0,
) -> None:
    terminal_states = {'completed', 'failed', 'cancelled'}

    for _ in range(max_attempts):
        response = await client.get(f'{base_url}/v1/orchestrate/runs/{run_id}', headers=headers)
        response.raise_for_status()
        payload = response.json()
        status = str(payload.get('status', '')).lower()
        if status in terminal_states:
            if status != 'completed':
                raise RuntimeError(f"Orchestrate run ended with status '{status}'.")
            return
        await asyncio.sleep(delay_seconds)

    raise TimeoutError('Timed out waiting for watsonx Orchestrate to finish the run.')


def _extract_latest_assistant_text(payload: Any) -> str:
    messages = payload if isinstance(payload, list) else payload.get('data', [])
    if not isinstance(messages, list):
        return ''

    for message in reversed(messages):
        if isinstance(message, dict) and message.get('role') == 'assistant':
            return _content_to_text(message.get('content'))
    return ''


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, dict):
        return _content_to_text(content.get('text') or content.get('content') or '')
    if isinstance(content, Iterable) and not isinstance(content, (str, bytes)):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get('response_type') == 'text':
                    parts.append(str(item.get('text', '')).strip())
                elif 'text' in item:
                    parts.append(str(item.get('text', '')).strip())
                elif 'content' in item:
                    parts.append(_content_to_text(item.get('content')))
            elif isinstance(item, str):
                parts.append(item.strip())
        return '\n'.join(part for part in parts if part)
    return ''


def _stub_response(topic_title: str, question: str) -> dict:
    return {
        'answer': (
            f"[Demo mode - Orchestrate not connected] This is where the live research answer about '{question}' would appear. "
            f"Once you add your watsonx Orchestrate credentials to .env.local, this chatbot will search the web and synthesize a real answer about {topic_title}."
        ),
        'sources': [
            {
                'title': 'watsonx Orchestrate - IBM',
                'url': 'https://www.ibm.com/products/watsonx-orchestrate',
                'excerpt': 'Add ORCHESTRATE_INSTANCE_URL, ORCHESTRATE_API_KEY, and ORCHESTRATE_AGENT_ID to .env.local.',
            }
        ],
    }
