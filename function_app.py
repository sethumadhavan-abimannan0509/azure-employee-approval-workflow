import azure.functions as func
import json
import os
import uuid
import logging
import urllib.request
import urllib.error
from azure.identity import DefaultAzureCredential

from azure.data.tables import TableServiceClient, UpdateMode

app = func.FunctionApp()



@app.route(route="submit-purchase", methods=["POST"])
def submit_purchase(req: func.HttpRequest) -> func.HttpResponse:

    try:
        # Step 1: Receive employee information
        data = req.get_json()

        employee_id = data.get("employee_id")
        employee_name = data.get("employee_name")
        item = data.get("item")
        amount = data.get("amount")

        # Step 2: Validate information
        if not all([
            employee_id,
            employee_name,
            item,
            amount is not None
        ]):
            return func.HttpResponse(
                "Missing required information",
                status_code=400
            )

        amount = float(amount)

        if amount <= 0:
            return func.HttpResponse(
                "Amount must be greater than zero",
                status_code=400
            )

        # Step 3: Connect to Azure Storage
        credential = DefaultAzureCredential()
        service = TableServiceClient(
            endpoint="https://rgemployeeapproval.table.core.windows.net",

            credential=credential

        )

        # Step 4: Access PurchaseRequests table
        table = service.create_table_if_not_exists(
            table_name="PurchaseRequests"
        )

        # Step 5: Create purchase request
        request_id = str(uuid.uuid4())

        entity = {
            "PartitionKey": "Employees",
            "RowKey": request_id,
            "EmployeeID": employee_id,
            "EmployeeName": employee_name,
            "Item": item,
            "Amount": amount,
            "Status": "Pending"
        }

        # Step 6: Save to Azure Table Storage
        table.create_entity(entity=entity)

        # Step 7: Trigger Logic App automatically
        logic_app_url = os.environ.get("LOGIC_APP_URL")

        if not logic_app_url:
            raise ValueError("LOGIC_APP_URL is not configured")

        payload = {
            "request_id": request_id,
            "employee_id": employee_id,
            "employee_name": employee_name,
            "item": item,
            "amount": amount
        }

        logic_app_data = json.dumps(payload).encode("utf-8")

        logic_app_request = urllib.request.Request(
            logic_app_url,
            data=logic_app_data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        with urllib.request.urlopen(
            logic_app_request,
            timeout=20
        ) as logic_response:

            logging.info(
                "Logic App triggered. HTTP status: %s",
                logic_response.status
            )

        # Step 8: Return confirmation
        response = {
            "message": "Purchase request submitted and approval workflow triggered",
            "request_id": request_id,
            "employee_id": employee_id,
            "item": item,
            "amount": amount,
            "status": "Pending"
        }

        return func.HttpResponse(
            json.dumps(response),
            status_code=201,
            mimetype="application/json"
        )

    except (ValueError, TypeError):
        logging.exception("Invalid purchase information")

        return func.HttpResponse(
            "Invalid JSON or purchase amount",
            status_code=400
        )

    except Exception:
        logging.exception("Purchase submission or workflow trigger failed")

        return func.HttpResponse(
            "Purchase processing failed. Check Function logs.",
            status_code=500
        )

@app.route(route="get-purchases", methods=["GET"])
def get_purchase_requests(req: func.HttpRequest) -> func.HttpResponse:

    try:
        # Connect to Azure Storage
        credential = DefaultAzureCredential()
        service = TableServiceClient(
            endpoint="https://rgemployeeapproval.table.core.windows.net",
            credential=credential
        )

        # Access PurchaseRequests table
        table = service.get_table_client(
            table_name="PurchaseRequests"
        )

        # Retrieve all purchase requests
        entities = table.list_entities()

        # Convert records into a list
        purchases = []

        for entity in entities:
            purchases.append({
                "employee_id": entity.get("EmployeeID"),
                "employee_name": entity.get("EmployeeName"),
                "item": entity.get("Item"),
                "amount": entity.get("Amount"),
                "status": entity.get("Status"),
                "request_id": entity.get("RowKey")
            })

        return func.HttpResponse(
            json.dumps(purchases),
            status_code=200,
            mimetype="application/json"
        )

    except Exception:
        logging.exception("Failed to retrieve purchase requests")

        return func.HttpResponse(
            "Unable to retrieve purchase requests",
            status_code=500
        )
@app.route(route="approve-purchase", methods=["POST"])
def approve_purchase(req: func.HttpRequest) -> func.HttpResponse:

    try:
        data = req.get_json()

        request_id = data.get("request_id")
        decision = data.get("decision")

        if not request_id or decision not in ["Approved", "Rejected"]:
            return func.HttpResponse(
                "Invalid request ID or decision",
                status_code=400
            )

        credential = DefaultAzureCredential()
        service = TableServiceClient(
            endpoint="https://rgemployeeapproval.table.core.windows.net",
            credential=credential
        )

        table = service.get_table_client(
            table_name="PurchaseRequests"
        )

        entity = table.get_entity(
            partition_key="Employees",
            row_key=request_id
        )

        entity["Status"] = decision

        table.update_entity(entity=entity, mode=UpdateMode.MERGE)

        response = {
            "message": "Purchase request updated successfully",
            "request_id": request_id,
            "status": decision
        }

        return func.HttpResponse(
            json.dumps(response),
            status_code=200,
            mimetype="application/json"
        )

    except Exception:
        logging.exception("Approval processing failed")

        return func.HttpResponse(
            "Unable to process approval",
            status_code=500
        )