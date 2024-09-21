import azure.functions as func
import azure.durable_functions as df
import logging
import requests
import json

API_VERSION = "2016-06-01"
GOOGLE_API_KEY = "your-google-api-key"  # Update with your API key

def handle_error(message, status_code=500):
    logging.error(message)
    return func.HttpResponse(message, status_code=status_code)

def get_google_response(workflow_code, error_details):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={GOOGLE_API_KEY}"
    
    messages = [
        {
            "text": f"Based on the following workflow code and errors, provide updated code:\n\nWorkflow Code: {json.dumps(workflow_code)}\nErrors: {json.dumps(error_details)} without code explaination. just raw updated code"
        }
    ]

    data = {
        "contents": [{"parts": messages}]
    }

    response = requests.post(url, headers={"Content-Type": "application/json"}, json=data)
    
    logging.info(f"Google API response: {response.status_code} - {response.text}")

    if response.status_code == 200:
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

# Activity Function to get workflow details
def get_workflow_details(activity_function_context, subscription_id, resource_group, workflow_name, headers):
    workflow_api_url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Logic/workflows/{workflow_name}?api-version={API_VERSION}"
    response = requests.get(workflow_api_url, headers=headers)
    response.raise_for_status()
    return response.json()

# Activity Function to get workflow runs
def get_workflow_runs(activity_function_context, subscription_id, resource_group, workflow_name, headers):
    runs_api_url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Logic/workflows/{workflow_name}/runs?api-version={API_VERSION}"
    response = requests.get(runs_api_url, headers=headers)
    response.raise_for_status()
    return response.json()

# Activity Function to get actions for a run
def get_actions_for_run(activity_function_context, run_id, subscription_id, resource_group, workflow_name, headers):
    actions_api_url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Logic/workflows/{workflow_name}/runs/{run_id}/actions?api-version={API_VERSION}"
    response = requests.get(actions_api_url, headers=headers)
    response.raise_for_status()
    return response.json()

# Orchestrator function
def orchestrator_function(context: df.DurableOrchestrationContext):
    request_data = context.get_input()

    subscription_id = request_data["subscription_id"]
    resource_group = request_data["resource_group"]
    workflow_name = request_data["workflow_name"]
    bearer_token = request_data["bearer_token"]

    headers = {
        'Authorization': bearer_token,
        'Content-Type': 'application/json'
    }

    # Get workflow details
    workflow_response = yield context.call_activity('get_workflow_details', {
        'subscription_id': subscription_id,
        'resource_group': resource_group,
        'workflow_name': workflow_name,
        'headers': headers
    })

    # Get workflow runs
    workflow_runs = yield context.call_activity('get_workflow_runs', {
        'subscription_id': subscription_id,
        'resource_group': resource_group,
        'workflow_name': workflow_name,
        'headers': headers
    })

    # Get actions for failed runs
    failed_run_actions = []
    for run in workflow_runs.get("value", []):
        properties = run.get("properties", {})
        status = properties.get("status")

        if status == "Failed":
            run_id = run.get("name")
            actions_data = yield context.call_activity('get_actions_for_run', {
                'run_id': run_id,
                'subscription_id': subscription_id,
                'resource_group': resource_group,
                'workflow_name': workflow_name,
                'headers': headers
            })

            workflow_error = []
            for action in actions_data.get("value", []):
                action_properties = action.get("properties", {})
                if action_properties.get("status") == "Failed":
                    error_message = action_properties.get("error", {}).get("message", "")
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

    if not failed_run_actions:
        return {"message": "No failed run actions found."}

    # Call Google API to get updated code
    updated_code = get_google_response(workflow_response, failed_run_actions)

    if updated_code is None:
        return {"error": "Failed to get updated code from Google API."}

    return {
        "failed_run_actions": failed_run_actions,
        "google_response": updated_code
    }

# HTTP trigger to start the orchestration
@app.route(route="http_trigger")
def http_trigger(req: func.HttpRequest, starter: str) -> func.HttpResponse:
    client = df.DurableOrchestrationClient(starter)

    bearer_token = req.headers.get('Authorization')
    if not bearer_token or not bearer_token.startswith('Bearer '):
        return handle_error("Invalid or missing Authorization token.", 400)

    try:
        req_body = req.get_json()
        subscription_id = req_body.get('subscription_id')
        resource_group = req_body.get('resource_group')
        workflow_name = req_body.get('workflow_name')

        if not all([subscription_id, resource_group, workflow_name]):
            return handle_error("Missing required parameters in the request body.", 400)
    except ValueError:
        return handle_error("Invalid JSON payload.", 400)

    orchestration_input = {
        "subscription_id": subscription_id,
        "resource_group": resource_group,
        "workflow_name": workflow_name,
        "bearer_token": bearer_token
    }

    instance_id = client.start_new('orchestrator_function', None, orchestration_input)

    return client.create_check_status_response(req, instance_id)
