import json
import os
import time
import urllib.parse
import urllib.request
import uuid

import boto3

from conf import perplexity_api_key, api_secret_key, firecrawl_api_key, serpapi_key

PERPLEXITY_SEARCH_URL = "https://api.perplexity.ai/search"
PERPLEXITY_CHAT_URL = "https://api.perplexity.ai/chat/completions"
SERPAPI_SEARCH_URL = "https://serpapi.com/search.json"
PERPLEXITY_DEFAULT_MAX_RESULTS = 3
PERPLEXITY_DEFAULT_MAX_TOKENS_PER_PAGE = 256
PERPLEXITY_CHAT_DEFAULT_MODEL = "sonar-pro"
PERPLEXITY_CHAT_DEFAULT_MAX_TOKENS = 4000
PERPLEXITY_CHAT_DEFAULT_TEMPERATURE = 0.1

BEDROCK_AGENT_ID = "CIARP5VKY3"
BEDROCK_AGENT_ALIAS_ID = "TSTALIASID"
BEDROCK_REGION = "us-east-1"
BEDROCK_JOBS_TABLE = os.environ.get("BEDROCK_JOBS_TABLE")
BEDROCK_WORKER_FUNCTION_NAME = os.environ.get("BEDROCK_WORKER_FUNCTION_NAME")
BEDROCK_JOB_TTL_SECONDS = 24 * 60 * 60
# The worker cannot run past its 900s Lambda timeout, so a job still pending
# well after that was killed before it could record a terminal state.
BEDROCK_JOB_STALE_SECONDS = 900 + 120

_bedrock_client = boto3.client("bedrock-agent-runtime", region_name=BEDROCK_REGION)
_lambda_client = boto3.client("lambda", region_name=BEDROCK_REGION)
_dynamodb = boto3.resource("dynamodb", region_name=BEDROCK_REGION)


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


def serpapi(event, context):
    """Proxy supported SerpAPI methods while keeping the API key server-side."""
    print('serpapi event: ', json.dumps(event))

    allowed_origin, error_response = _validate_request(event)
    if error_response:
        return error_response

    event_body = event.get("body", None)
    if event_body is not None:
        try:
            body_data = json.loads(event_body)
        except json.JSONDecodeError:
            return {
                "statusCode": 400,
                "status": "error",
                "body": json.dumps({"error": "Invalid JSON in request body"}),
                "headers": {
                    'Access-Control-Allow-Origin': allowed_origin,
                    'Content-Type': 'application/json'
                }
            }
    else:
        body_data = event

    method = body_data.get("method")
    if method != "search.json":
        return {
            "statusCode": 400,
            "status": "error",
            "body": json.dumps({
                "error": "Unsupported method",
                "supportedMethods": ["search.json"]
            }),
            "headers": {
                'Access-Control-Allow-Origin': allowed_origin,
                'Content-Type': 'application/json'
            }
        }

    params = body_data.get("params")
    if not isinstance(params, dict):
        return {
            "statusCode": 400,
            "status": "error",
            "body": json.dumps({"error": "params must be an object"}),
            "headers": {
                'Access-Control-Allow-Origin': allowed_origin,
                'Content-Type': 'application/json'
            }
        }

    query = str(params.get("q") or "").strip()
    if not query:
        return {
            "statusCode": 400,
            "status": "error",
            "body": json.dumps({"error": "params.q is required"}),
            "headers": {
                'Access-Control-Allow-Origin': allowed_origin,
                'Content-Type': 'application/json'
            }
        }

    if not serpapi_key:
        print('ERROR: serpapi_key not configured in conf.py')
        return {
            "statusCode": 500,
            "status": "error",
            "body": json.dumps({"error": "Server configuration error"}),
            "headers": {
                'Access-Control-Allow-Origin': allowed_origin,
                'Content-Type': 'application/json'
            }
        }

    request_params = {
        "gl": "il",
        "hl": "he",
        "num": 20,
        **params,
        "api_key": serpapi_key,
    }
    url = f"{SERPAPI_SEARCH_URL}?{urllib.parse.urlencode(request_params, doseq=True)}"

    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            response_data = resp.read().decode('utf-8')

        print(f'SerpAPI response length: {len(response_data)} characters')

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
        print(f"SerpAPI error ({e.code}): {error_body}")
        return {
            "statusCode": e.code,
            "status": "error",
            "body": json.dumps({"error": f"SerpAPI error: {error_body}"}),
            "headers": {
                'Access-Control-Allow-Origin': allowed_origin,
                'Content-Type': 'application/json'
            }
        }
    except Exception as e:
        print(f"Error with SerpAPI: {str(e)}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return {
            "statusCode": 500,
            "status": "error",
            "body": json.dumps({"error": f"Failed to search SerpAPI: {str(e)}"}),
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


def _json_response(status_code, payload, allowed_origin):
    """Build an API Gateway response in the shape this API returns everywhere."""
    return {
        "statusCode": status_code,
        "status": "success" if status_code < 400 else "error",
        "body": json.dumps(payload, default=str),
        "headers": {
            'Access-Control-Allow-Origin': allowed_origin,
            'Content-Type': 'application/json'
        }
    }


def _bedrock_jobs_table():
    return _dynamodb.Table(BEDROCK_JOBS_TABLE)


def _update_bedrock_job(job_id, attributes):
    """Write the outcome of an agent run onto its job record."""
    _bedrock_jobs_table().update_item(
        Key={"jobId": job_id},
        UpdateExpression="SET " + ", ".join(f"#{key} = :{key}" for key in attributes),
        ExpressionAttributeNames={f"#{key}": key for key in attributes},
        ExpressionAttributeValues={f":{key}": value for key, value in attributes.items()},
    )


def bedrock_chat(event, context):
    """Queue an Amazon Bedrock Agent run and return a job id the client polls."""
    print('bedrock chat event: ', json.dumps(event))

    allowed_origin, error_response = _validate_request(event)
    if error_response:
        return error_response

    event_body = event.get("body", None)
    request = json.loads(event_body) if event_body is not None else event

    message = request.get("message")
    user_profile = request.get("userProfile") or {}

    if not message:
        return _json_response(400, {"error": "No message provided"}, allowed_origin)

    job_id = str(uuid.uuid4())
    # A shared session id would leak conversation state between unrelated users,
    # so callers that want a multi-turn conversation must supply their own.
    session_id = request.get("sessionId") or f"session-{job_id}"

    try:
        created_at = int(time.time())
        _bedrock_jobs_table().put_item(Item={
            "jobId": job_id,
            "status": "pending",
            "createdAt": created_at,
            "expiresAt": created_at + BEDROCK_JOB_TTL_SECONDS,
        })

        _lambda_client.invoke(
            FunctionName=BEDROCK_WORKER_FUNCTION_NAME,
            InvocationType="Event",
            Payload=json.dumps({
                "jobId": job_id,
                "message": message,
                "sessionId": session_id,
                "userProfile": user_profile,
            }).encode("utf-8"),
        )

        print(f'Queued Bedrock agent job {job_id} (session={session_id}): {message[:200]}...')

        return _json_response(202, {"jobId": job_id, "status": "pending"}, allowed_origin)

    except Exception as e:
        print(f"Error queueing Bedrock agent job: {str(e)}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return _json_response(500, {"error": f"Failed to queue Bedrock agent job: {str(e)}"}, allowed_origin)


def bedrock_chat_worker(event, context):
    """Run the Bedrock Agent to completion and store the result for polling."""
    print('bedrock chat worker event: ', json.dumps(event))

    job_id = event.get("jobId")
    message = event.get("message")
    session_id = event.get("sessionId")
    user_profile = event.get("userProfile") or {}

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
            enableTrace=True,
        )

        full_response = ""
        return_control = None
        files = []

        for stream_event in response["completion"]:
            print(f'Bedrock stream event: {next(iter(stream_event), None)}')

            chunk = stream_event.get("chunk")
            if chunk and chunk.get("bytes"):
                full_response += chunk["bytes"].decode("utf-8")

            if "returnControl" in stream_event:
                return_control = stream_event["returnControl"]
                print(f'Agent handed control back: {json.dumps(return_control, default=str)}')

            if "files" in stream_event:
                for file_entry in stream_event["files"].get("files", []):
                    files.append({"name": file_entry.get("name"), "type": file_entry.get("type")})
                print(f'Agent returned files: {json.dumps(files)}')

            if "trace" in stream_event:
                trace = stream_event["trace"].get("trace", {})
                for trace_type, trace_body in trace.items():
                    print(f'Trace {trace_type}: {json.dumps(trace_body, default=str)[:2000]}')

        print(f'Bedrock agent response length: {len(full_response)} characters')

        if return_control is not None:
            _update_bedrock_job(job_id, {
                "status": "failed",
                "error": "Agent paused for action confirmation; nothing can answer it from here.",
                "completedAt": int(time.time()),
            })
            return

        _update_bedrock_job(job_id, {
            "status": "completed",
            "response": full_response,
            "files": files,
            "completedAt": int(time.time()),
        })

    except Exception as e:
        print(f"Error invoking Bedrock agent: {str(e)}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        _update_bedrock_job(job_id, {
            "status": "failed",
            "error": str(e),
            "completedAt": int(time.time()),
        })


def bedrock_chat_status(event, context):
    """Report the status, and once finished the result, of a queued agent run."""
    print('bedrock chat status event: ', json.dumps(event))

    allowed_origin, error_response = _validate_request(event)
    if error_response:
        return error_response

    event_body = event.get("body", None)
    request = json.loads(event_body) if event_body is not None else event
    job_id = request.get("jobId") or request.get("id")

    if not job_id:
        return _json_response(400, {"error": "No job id provided"}, allowed_origin)

    try:
        job = _bedrock_jobs_table().get_item(Key={"jobId": job_id}).get("Item")

        if not job:
            return _json_response(404, {"error": f"Unknown job id: {job_id}"}, allowed_origin)

        status = job.get("status")
        error = job.get("error")
        # createdAt comes back as a Decimal, which will not do arithmetic with a float.
        created_at = int(job.get("createdAt") or 0)
        age_seconds = int(time.time()) - created_at

        if status == "pending" and created_at and age_seconds > BEDROCK_JOB_STALE_SECONDS:
            status = "failed"
            error = f"Agent run went quiet for {age_seconds}s; the worker was killed before it could finish."

        print(f'Bedrock agent job {job_id} status: {status} (age {age_seconds}s)')

        return _json_response(200, {
            "jobId": job_id,
            "status": status,
            "response": job.get("response", ""),
            "files": job.get("files", []),
            "error": error,
        }, allowed_origin)

    except Exception as e:
        print(f"Error reading Bedrock agent job: {str(e)}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return _json_response(500, {"error": f"Failed to read job status: {str(e)}"}, allowed_origin)
