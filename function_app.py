import azure.functions as func 
import logging
import requests
import json
import concurrent.futures

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

API_VERSION = "2016-06-01"
GOOGLE_API_KEY = "AIzaSyCSUcI9ZlnwiswT4LQFL6uwTeJpTUXmG0g"  # Update with your API key

def handle_error(message, status_code=500):
    logging.error(message)
    return func.HttpResponse(message, status_code=status_code)

def get_google_response(workflow_code, error_details):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={GOOGLE_API_KEY}"
    
    messages = [
        {
            "text": f"Based on the following workflow code and errors, provide updated code:\n\nWorkflow Code: {json.dumps(workflow_code)}\nErrors: {json.dumps(error_details)}"
        }
    ]

    data = {
        "contents": [{"parts": messages}]
    }

    response = requests.post(url, headers={"Content-Type": "application/json"}, json=data)
    
    # Log the full response for debugging
    logging.info(f"Google API response: {response.status_code} - {response.text}")

    if response.status_code == 200:
        # Extract only the updated code without explanations
        candidates = response.json().get('candidates', [])
        if candidates:
            return {
                "updatedcode": {
                    "text": candidates[0].get('content', {}).get('parts', [{}])[0].get('text', "")
                }
            }
    else:
        logging.error(f"Google API request failed: {response.status_code} - {response.text}")
        return None

@app.route(route="http_trigger")
def http_trigger(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    bearer_token = req.headers.get('Authorization')
    if not bearer_token or not bearer_token.startswith('Bearer '):
        return handle_error("Invalid or missing Authorization token.", 400)

    # Extract parameters from request body
    try:
        req_body = req.get_json()
        subscription_id = req_body.get('subscription_id')
        resource_group = req_body.get('resource_group')
        workflow_name = req_body.get('workflow_name')

        if not all([subscription_id, resource_group, workflow_name]):
            return handle_error("Missing required parameters in the request body.", 400)
    except ValueError:
        return handle_error("Invalid JSON payload.", 400)

    RUNS_API_URL = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Logic/workflows/{workflow_name}/runs?api-version={API_VERSION}"
    ACTIONS_API_URL_TEMPLATE = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Logic/workflows/{workflow_name}/runs/{{run_id}}/actions?api-version={API_VERSION}"
    WORKFLOW_API_URL = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Logic/workflows/{workflow_name}?api-version={API_VERSION}"

    headers = {
        'Authorization': bearer_token,
        'Content-Type': 'application/json'
    }

    def get_actions(run_id):
        actions_url = ACTIONS_API_URL_TEMPLATE.format(run_id=run_id)
        response = requests.get(actions_url, headers=headers)
        response.raise_for_status()
        return response.json()

    def get_workflow():
        response = requests.get(WORKFLOW_API_URL, headers=headers)
        response.raise_for_status()
        return response.json()

    try:
        response = requests.get(RUNS_API_URL, headers=headers)
        response.raise_for_status()
        api_response = response.json()
    except requests.exceptions.RequestException as e:
        return handle_error(f"API call to get runs failed: {str(e)}")

    failed_run_actions = []
    seen_error_messages = set()

    with concurrent.futures.ThreadPoolExecutor() as executor:
        workflow_future = executor.submit(get_workflow)

        for run in api_response.get("value", []):
            properties = run.get("properties", {})
            status = properties.get("status")

            if status == "Failed":
                run_id = run.get("name")
                logging.info(f"Found failed run ID: {run_id}")

                try:
                    actions_future = executor.submit(get_actions, run_id)
                    actions_data = actions_future.result()

                    workflow_error = []
                    for action in actions_data.get("value", []):
                        action_properties = action.get("properties", {})
                        if action_properties.get("status") == "Failed":
                            error_message = action_properties.get("error", {}).get("message", "")
                            if error_message not in seen_error_messages:
                                seen_error_messages.add(error_message)
                                error_detail = {
                                    "properties": {
                                        "status": action_properties.get("status"),
                                        "code": action_properties.get("code"),
                                        "error": action_properties.get("error", {})
                                    },
                                    "name": action.get("name"),
                                    "type": action.get("type")
                                }
                                workflow_error.append(error_detail)

                    if workflow_error:
                        failed_run_actions.append({run_id: {"workflow-error": workflow_error}})

                except requests.exceptions.RequestException as e:
                    logging.error(f"API call to get actions for run ID {run_id} failed: {str(e)}")

        try:
            workflow_response = workflow_future.result()
        except Exception as e:
            return handle_error(f"Failed to get workflow details: {str(e)}")

        workflow_code = {
            "definition": workflow_response.get("properties", {}).get("definition", {}),
            "parameters": workflow_response.get("properties", {}).get("parameters", {})
        }

    if not failed_run_actions:
        return func.HttpResponse("No failed run actions found.", status_code=200)

    updated_code = get_google_response(workflow_code, failed_run_actions)

    if updated_code is None:
        return handle_error("Failed to get updated code from Google API.", 500)

    return func.HttpResponse(
        json.dumps({
            "failed_run_actions": failed_run_actions,
            "google_response": updated_code
        }),
        status_code=200,
        mimetype="application/json"
    )
