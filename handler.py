import json
import urllib.request

import boto3

from conf import perplexity_api_key, api_secret_key, firecrawl_api_key

PERPLEXITY_SEARCH_URL = "https://api.perplexity.ai/search"
PERPLEXITY_CHAT_URL = "https://api.perplexity.ai/chat/completions"
PERPLEXITY_DEFAULT_MAX_RESULTS = 3
PERPLEXITY_DEFAULT_MAX_TOKENS_PER_PAGE = 256
PERPLEXITY_CHAT_DEFAULT_MODEL = "sonar-pro"
PERPLEXITY_CHAT_DEFAULT_MAX_TOKENS = 4000
PERPLEXITY_CHAT_DEFAULT_TEMPERATURE = 0.1

BEDROCK_AGENT_ID = "CIARP5VKY3"
BEDROCK_AGENT_ALIAS_ID = "TSTALIASID"
BEDROCK_REGION = "us-east-1"
BEDROCK_DEFAULT_SESSION_ID = "default-session"

_bedrock_client = boto3.client("bedrock-agent-runtime", region_name=BEDROCK_REGION)


def _validate_request(event):
    """Shared validation for origin and API key. Returns (allowed_origin, error_response)."""
    event_headers = event.get("headers", None)
    event_origin = event_headers.get("origin", None) if event_headers else None

    if api_secret_key:
        provided_api_key = event_headers.get("x-api-key") if event_headers else None
        if not provided_api_key or provided_api_key != api_secret_key:
            print('Invalid or missing API key')
            return None, {
                "statusCode": 403,
                "body": json.dumps({"error": "Invalid or missing API key"}),
                "headers": {
                    'Access-Control-Allow-Origin': '*',
                    'Content-Type': 'application/json'
                }
            }

    allowed_origin = 'https://broadcust.co.il'
    if event_origin is not None:
        if event_origin.endswith("broadcust.co.il"):
            allowed_origin = event_origin
        else:
            print('origin is not allowed: ', event_origin)
            return None, {
                "statusCode": 403,
                'error': "Invalid Origin"
            }

    return allowed_origin, None


def perplexity_search(event, context):
    """Search using Perplexity Search API"""
    print('perplexity search event: ', json.dumps(event))

    allowed_origin, error_response = _validate_request(event)
    if error_response:
        return error_response

    event_body = event.get("body", None)

    if event_body is not None:
        event_body_json_load = json.loads(event_body)
        query = event_body_json_load.get("query") or event_body_json_load.get("prompt")
        max_results = event_body_json_load.get("max_results", PERPLEXITY_DEFAULT_MAX_RESULTS)
        max_tokens_per_page = event_body_json_load.get("max_tokens_per_page", PERPLEXITY_DEFAULT_MAX_TOKENS_PER_PAGE)
    else:
        query = event.get("query") or event.get("prompt")
        max_results = event.get("max_results", PERPLEXITY_DEFAULT_MAX_RESULTS)
        max_tokens_per_page = event.get("max_tokens_per_page", PERPLEXITY_DEFAULT_MAX_TOKENS_PER_PAGE)

    if not query:
        return {
            "statusCode": 400,
            "status": "error",
            "body": json.dumps({"error": "No query provided"}),
            "headers": {
                'Access-Control-Allow-Origin': allowed_origin,
                'Content-Type': 'application/json'
            }
        }

    try:
        print(f'Searching Perplexity for: {query}')

        payload = json.dumps({
            "query": query,
            "max_results": max_results,
            "max_tokens_per_page": max_tokens_per_page
        }).encode('utf-8')

        req = urllib.request.Request(
            PERPLEXITY_SEARCH_URL,
            data=payload,
            headers={
                "Authorization": f"Bearer {perplexity_api_key}",
                "Content-Type": "application/json"
            },
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=25) as resp:
            response_data = resp.read().decode('utf-8')

        print(f'Perplexity response length: {len(response_data)} characters')

        return {
            "statusCode": 200,
            "status": "success",
            "body": response_data,
            "headers": {
                'Access-Control-Allow-Origin': allowed_origin,
                'Content-Type': 'application/json'
            }
        }

    except urllib.request.HTTPError as e:
        error_body = e.read().decode('utf-8') if e.fp else str(e)
        print(f"Perplexity API error ({e.code}): {error_body}")
        return {
            "statusCode": e.code,
            "status": "error",
            "body": json.dumps({"error": f"Perplexity API error: {error_body}"}),
            "headers": {
                'Access-Control-Allow-Origin': allowed_origin,
                'Content-Type': 'application/json'
            }
        }
    except Exception as e:
        print(f"Error with Perplexity search: {str(e)}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return {
            "statusCode": 500,
            "status": "error",
            "body": json.dumps({"error": f"Failed to search: {str(e)}"}),
            "headers": {
                'Access-Control-Allow-Origin': allowed_origin,
                'Content-Type': 'application/json'
            }
        }


def perplexity_chat(event, context):
    """Chat completions using Perplexity Sonar Pro"""
    print('perplexity chat event: ', json.dumps(event))

    allowed_origin, error_response = _validate_request(event)
    if error_response:
        return error_response

    event_body = event.get("body", None)

    if event_body is not None:
        event_body_json_load = json.loads(event_body)
        prompt = event_body_json_load.get("prompt") or event_body_json_load.get("query")
        model = event_body_json_load.get("model", PERPLEXITY_CHAT_DEFAULT_MODEL)
        max_tokens = event_body_json_load.get("max_tokens", PERPLEXITY_CHAT_DEFAULT_MAX_TOKENS)
        temperature = event_body_json_load.get("temperature", PERPLEXITY_CHAT_DEFAULT_TEMPERATURE)
    else:
        prompt = event.get("prompt") or event.get("query")
        model = event.get("model", PERPLEXITY_CHAT_DEFAULT_MODEL)
        max_tokens = event.get("max_tokens", PERPLEXITY_CHAT_DEFAULT_MAX_TOKENS)
        temperature = event.get("temperature", PERPLEXITY_CHAT_DEFAULT_TEMPERATURE)

    if not prompt:
        return {
            "statusCode": 400,
            "status": "error",
            "body": json.dumps({"error": "No prompt provided"}),
            "headers": {
                'Access-Control-Allow-Origin': allowed_origin,
                'Content-Type': 'application/json'
            }
        }

    try:
        print(f'Perplexity chat with model {model}: {prompt[:200]}...')

        payload = json.dumps({
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": max_tokens,
            "temperature": temperature
        }).encode('utf-8')

        req = urllib.request.Request(
            PERPLEXITY_CHAT_URL,
            data=payload,
            headers={
                "Authorization": f"Bearer {perplexity_api_key}",
                "Content-Type": "application/json"
            },
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=25) as resp:
            response_data = resp.read().decode('utf-8')

        print(f'Perplexity chat response length: {len(response_data)} characters')

        return {
            "statusCode": 200,
            "status": "success",
            "body": response_data,
            "headers": {
                'Access-Control-Allow-Origin': allowed_origin,
                'Content-Type': 'application/json'
            }
        }

    except urllib.request.HTTPError as e:
        error_body = e.read().decode('utf-8') if e.fp else str(e)
        print(f"Perplexity chat API error ({e.code}): {error_body}")
        return {
            "statusCode": e.code,
            "status": "error",
            "body": json.dumps({"error": f"Perplexity API error: {error_body}"}),
            "headers": {
                'Access-Control-Allow-Origin': allowed_origin,
                'Content-Type': 'application/json'
            }
        }
    except Exception as e:
        print(f"Error with Perplexity chat: {str(e)}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return {
            "statusCode": 500,
            "status": "error",
            "body": json.dumps({"error": f"Failed to chat: {str(e)}"}),
            "headers": {
                'Access-Control-Allow-Origin': allowed_origin,
                'Content-Type': 'application/json'
            }
        }


FIRECRAWL_BATCH_SCRAPE_URL = "https://api.firecrawl.dev/v2/batch/scrape"


def firecrawl_batch_scrape(event, context):
    """Start a Firecrawl batch scrape job"""
    print('firecrawl batch scrape event: ', json.dumps(event))

    allowed_origin, error_response = _validate_request(event)
    if error_response:
        return error_response

    event_body = event.get("body", None)

    if event_body is not None:
        event_body_json_load = json.loads(event_body)
        urls = event_body_json_load.get("urls")
        formats = event_body_json_load.get("formats", ["json"])
        only_main_content = event_body_json_load.get("onlyMainContent", True)
    else:
        urls = event.get("urls")
        formats = event.get("formats", ["json"])
        only_main_content = event.get("onlyMainContent", True)

    if not urls or not isinstance(urls, list):
        return {
            "statusCode": 400,
            "status": "error",
            "body": json.dumps({"error": "No urls provided. Expected a list of URLs."}),
            "headers": {
                'Access-Control-Allow-Origin': allowed_origin,
                'Content-Type': 'application/json'
            }
        }

    try:
        print(f'Starting Firecrawl batch scrape for {len(urls)} URLs')

        payload = json.dumps({
            "urls": urls,
            "formats": formats,
            "onlyMainContent": only_main_content
        }).encode('utf-8')

        req = urllib.request.Request(
            FIRECRAWL_BATCH_SCRAPE_URL,
            data=payload,
            headers={
                "Authorization": f"Bearer {firecrawl_api_key}",
                "Content-Type": "application/json"
            },
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=25) as resp:
            response_data = resp.read().decode('utf-8')

        print(f'Firecrawl batch scrape started: {response_data}')

        return {
            "statusCode": 200,
            "status": "success",
            "body": response_data,
            "headers": {
                'Access-Control-Allow-Origin': allowed_origin,
                'Content-Type': 'application/json'
            }
        }

    except urllib.request.HTTPError as e:
        error_body = e.read().decode('utf-8') if e.fp else str(e)
        print(f"Firecrawl API error ({e.code}): {error_body}")
        return {
            "statusCode": e.code,
            "status": "error",
            "body": json.dumps({"error": f"Firecrawl API error: {error_body}"}),
            "headers": {
                'Access-Control-Allow-Origin': allowed_origin,
                'Content-Type': 'application/json'
            }
        }
    except Exception as e:
        print(f"Error with Firecrawl batch scrape: {str(e)}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return {
            "statusCode": 500,
            "status": "error",
            "body": json.dumps({"error": f"Failed to start batch scrape: {str(e)}"}),
            "headers": {
                'Access-Control-Allow-Origin': allowed_origin,
                'Content-Type': 'application/json'
            }
        }


def firecrawl_batch_status(event, context):
    """Check status of a Firecrawl batch scrape job"""
    print('firecrawl batch status event: ', json.dumps(event))

    allowed_origin, error_response = _validate_request(event)
    if error_response:
        return error_response

    event_body = event.get("body", None)

    if event_body is not None:
        event_body_json_load = json.loads(event_body)
        batch_id = event_body_json_load.get("id")
    else:
        batch_id = event.get("id")

    if not batch_id:
        return {
            "statusCode": 400,
            "status": "error",
            "body": json.dumps({"error": "No batch job id provided"}),
            "headers": {
                'Access-Control-Allow-Origin': allowed_origin,
                'Content-Type': 'application/json'
            }
        }

    try:
        status_url = f"{FIRECRAWL_BATCH_SCRAPE_URL}/{batch_id}"
        print(f'Checking Firecrawl batch status: {batch_id}')

        req = urllib.request.Request(
            status_url,
            headers={
                "Authorization": f"Bearer {firecrawl_api_key}",
                "Content-Type": "application/json"
            },
            method="GET"
        )

        with urllib.request.urlopen(req, timeout=25) as resp:
            response_data = resp.read().decode('utf-8')

        print(f'Firecrawl batch status response length: {len(response_data)} characters')

        return {
            "statusCode": 200,
            "status": "success",
            "body": response_data,
            "headers": {
                'Access-Control-Allow-Origin': allowed_origin,
                'Content-Type': 'application/json'
            }
        }

    except urllib.request.HTTPError as e:
        error_body = e.read().decode('utf-8') if e.fp else str(e)
        print(f"Firecrawl status API error ({e.code}): {error_body}")
        return {
            "statusCode": e.code,
            "status": "error",
            "body": json.dumps({"error": f"Firecrawl API error: {error_body}"}),
            "headers": {
                'Access-Control-Allow-Origin': allowed_origin,
                'Content-Type': 'application/json'
            }
        }
    except Exception as e:
        print(f"Error checking Firecrawl batch status: {str(e)}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return {
            "statusCode": 500,
            "status": "error",
            "body": json.dumps({"error": f"Failed to check batch status: {str(e)}"}),
            "headers": {
                'Access-Control-Allow-Origin': allowed_origin,
                'Content-Type': 'application/json'
            }
        }


def bedrock_chat(event, context):
    """Chat with an Amazon Bedrock Agent and return the concatenated streamed response."""
    print('bedrock chat event: ', json.dumps(event))

    allowed_origin, error_response = _validate_request(event)
    if error_response:
        return error_response

    event_body = event.get("body", None)

    if event_body is not None:
        event_body_json_load = json.loads(event_body)
        message = event_body_json_load.get("message")
        session_id = event_body_json_load.get("sessionId") or BEDROCK_DEFAULT_SESSION_ID
        user_profile = event_body_json_load.get("userProfile") or {}
    else:
        message = event.get("message")
        session_id = event.get("sessionId") or BEDROCK_DEFAULT_SESSION_ID
        user_profile = event.get("userProfile") or {}

    if not message:
        return {
            "statusCode": 400,
            "status": "error",
            "body": json.dumps({"error": "No message provided"}),
            "headers": {
                'Access-Control-Allow-Origin': allowed_origin,
                'Content-Type': 'application/json'
            }
        }

    session_attributes = {
        "userName": user_profile.get("name") or "",
        "businessName": user_profile.get("business") or "",
        "email": user_profile.get("email") or "",
    }

    try:
        print(f'Invoking Bedrock agent {BEDROCK_AGENT_ID} (session={session_id}): {message[:200]}...')

        response = _bedrock_client.invoke_agent(
            agentId=BEDROCK_AGENT_ID,
            agentAliasId=BEDROCK_AGENT_ALIAS_ID,
            sessionId=session_id,
            inputText=message,
            sessionState={"sessionAttributes": session_attributes},
        )

        full_response = ""
        for stream_event in response["completion"]:
            chunk = stream_event.get("chunk")
            if chunk and chunk.get("bytes"):
                full_response += chunk["bytes"].decode("utf-8")

        print(f'Bedrock agent response length: {len(full_response)} characters')

        return {
            "statusCode": 200,
            "status": "success",
            "body": json.dumps({"response": full_response}),
            "headers": {
                'Access-Control-Allow-Origin': allowed_origin,
                'Content-Type': 'application/json'
            }
        }

    except Exception as e:
        print(f"Error invoking Bedrock agent: {str(e)}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return {
            "statusCode": 500,
            "status": "error",
            "body": json.dumps({"error": f"Failed to invoke Bedrock agent: {str(e)}"}),
            "headers": {
                'Access-Control-Allow-Origin': allowed_origin,
                'Content-Type': 'application/json'
            }
        }
