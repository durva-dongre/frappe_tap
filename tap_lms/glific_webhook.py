import frappe
from frappe import _
import json
import requests
from .glific_integration import get_glific_auth_headers, get_glific_settings,create_contact,get_contact_by_phone,send_glific_update
from .api import get_model_for_school

@frappe.whitelist()
def update_glific_contact(doc, method):
    
    # used for debugging purposes
    frappe.logger().error("\n\nInside update_glific_contact function\n\n")
    frappe.logger().error(f"Doc: {doc}\n\n")


    if doc.doctype != "Teacher":
        frappe.logger().error(f"update_glific_contact called with invalid doctype {doc.doctype}\n")
        return

    try:
        #! new code using phone number
        # Use get_contact_by_phone instead of get_glific_contact
        glific_contact = get_contact_by_phone(doc.phone_number)
        frappe.logger().error(f"\nFetched Glific contact using get_contact_by_phone(): {glific_contact}\n")
        
        if not glific_contact:
            frappe.logger().error(f"\nGlific contact not found for teacher {doc.name} with phone {doc.phone_number}\n")
            return

        # Update the glific_id if it's not set
        if not doc.glific_id and 'id' in glific_contact:
            doc.glific_id = glific_contact['id']
            doc.save(ignore_permissions=True)
            frappe.logger().error(f"Updated Glific ID for teacher {doc.name} to {doc.glific_id}\n")



        # ! CHECK: automatically create a new teacher in glific after adding to frappe
        # if not doc.glific_id:
        #     frappe.logger().warning(f"No Glific ID found for teacher {doc.name}. Attempting to create or find Glific contact.")
        #     glific_contact = create_or_get_glific_contact(doc)
        #     if glific_contact and 'id' in glific_contact:
        #         doc.glific_id = glific_contact['id']
        #         doc.save(ignore_permissions=True)
        #     else:
        #         frappe.logger().error(f"Failed to create or find Glific contact for teacher {doc.name}")
        #         return

        
        # # Fetch Glific contact details
        # glific_contact = get_glific_contact(doc.glific_id)
        # frappe.logger().info(f"Fetched Glific contact using get_glific_contact(): {glific_contact}")
        # if not glific_contact:
        #     #! this is the error i am getting while creating a new teacher as it gets created in frappe but not in glific
        #     frappe.logger().error(f"Glific contact not found for teacher {doc.name}")
        #     return



        # Prepare update payload
        update_payload = prepare_update_payload(doc, glific_contact)
        if not update_payload:
            frappe.logger().info(f"No updates needed for Glific contact {doc.glific_id}\n")
            #! used for debugging purposes
            frappe.logger().error(f"No updates needed for Glific contact {doc.glific_id}\n")
            return

        # Send update to Glific
        success = send_glific_update(doc.glific_id, update_payload)
        if success:
            frappe.logger().info(f"Successfully updated Glific contact for teacher {doc.name}\n")
            #! used for debugging purposes
            frappe.logger().error(f"Successfully updated Glific contact for teacher {doc.name}\n")
        else:
            frappe.logger().error(f"Failed to update Glific contact for teacher {doc.name}\n")

    except Exception as e:
        frappe.logger().error(f"\nError updating Glific contact for teacher {doc.name}: {str(e)}")

def get_glific_contact(glific_id):
    settings = get_glific_settings()
    url = f"{settings.api_url}/api"
    headers = get_glific_auth_headers()
    
    query = """
    query contact($id: ID!) {
      contact(id: $id) {
        contact {
          id
          name
          language {
            id
            label
          }
          fields
        }
      }
    }
    """
    
    variables = {"id": glific_id}
    
    try:
        response = requests.post(url, json={"query": query, "variables": variables}, headers=headers)
        if response.status_code == 200:
            data = response.json()
            contact_data = data.get("data", {}).get("contact", {}).get("contact")
            if not contact_data:
                frappe.logger().error(f"No contact data found for ID {glific_id}")
                return None
            frappe.logger().error(f"Fetched Glific contact data successfully: {contact_data}")
            return contact_data
        return None
    except Exception as e:
        frappe.logger().error(f"Error fetching Glific contact: {str(e)}")
        return None





def prepare_update_payload(doc, glific_contact):
    """
    Prepares the payload for updating a Glific contact.
    
    Args:
        doc: Frappe document (Teacher)
        glific_contact: Glific contact data
        
    Returns:
        dict: Update payload if there are changes, None otherwise
    """

    # Validate input parameters
    if not doc or not glific_contact:
        frappe.logger().error("Missing required parameters: doc or glific_contact")
        return None

    # fetch field mappings 
    field_mappings = frappe.get_all(
        "Glific Field Mapping",
        filters={"frappe_doctype": "Teacher"},
        fields=["frappe_field", "glific_field"]
    )

    if not field_mappings:
        frappe.logger().error("No field mappings found for Teacher")
        return None

    # current_fields = json.loads(glific_contact.get("fields", "{}"))
    #! Parse and validate current fields
    try:
        current_fields = json.loads(glific_contact.get("fields", "{}"))
        if not isinstance(current_fields, dict):
            frappe.logger().error(f"Invalid fields format in glific_contact: {current_fields}")
            current_fields = {}
    except json.JSONDecodeError as e:
        frappe.logger().error(f"Error parsing glific_contact fields: {str(e)}")
        current_fields = {}

    # Start with a copy of all existing fields
    update_fields = current_fields.copy()  
    has_updates = False

    #! Log initial state for debugging
    frappe.logger().error(f"Initial fields state: {update_fields}")

    for mapping in field_mappings:
        frappe_value = doc.get(mapping.frappe_field)
        glific_field = mapping.glific_field
        
        #! Log field mapping processing
        frappe.logger().error(f"\nProcessing mapping: {mapping.frappe_field} -> {glific_field}")
        frappe.logger().error(f"Current value: {frappe_value}")

        #! Skip if frappe value is None
        if frappe_value is None:
            frappe.logger().debug(f"Skipping {mapping.frappe_field} as value is None")
        
        if glific_field in current_fields:
            if frappe_value != current_fields[glific_field].get("value"):
                update_fields[glific_field] = {
                    "value": frappe_value,
                    "type": "string",
                    "inserted_at": frappe.utils.now_datetime().isoformat()
                }
                has_updates = True
                frappe.logger().error(f"Updated {glific_field} to {frappe_value}")
        else:
            update_fields[glific_field] = {
                "value": frappe_value,
                "type": "string",
                "inserted_at": frappe.utils.now_datetime().isoformat()
            }
            has_updates = True
            frappe.logger().error(f"Updated Glific Field:'{glific_field}' with value: '{frappe_value}'")

    # Handle language change
    frappe_language = doc.get("language")
    if not frappe_language:
            frappe.logger().warning("No language specified in Teacher document")
    else:
        glific_language_id = frappe.db.get_value(
            "TAP Language", 
            {"language_name": frappe_language},
             "glific_language_id"
        )
        # ! need to check if the language is being fetched correctly
        frappe.logger().error(f"\nfrappe_language: {frappe_language} \n glific_language_id: {glific_language_id}")

    payload = {}
    
    if glific_language_id and int(glific_language_id) != int(glific_contact["language"]["id"]):
        payload["languageId"] = int(glific_language_id)
        has_updates = True

    if has_updates:
        payload["fields"] = json.dumps(update_fields)

    #! used for debugging purposes (MAKE SURE TO CHECK WHETHER THE PAYLOAD IS BEING GENERATED CORRECTLY)
    frappe.logger().error(f"\n\nupdate_payload: {payload}\n\n")
    return payload if has_updates else None






def send_glific_update(glific_id, update_payload):
    settings = get_glific_settings()
    url = f"{settings.api_url}/api"
    headers = get_glific_auth_headers()

    query = """
    mutation updateContact($id: ID!, $input: ContactInput!) {
      updateContact(id: $id, input: $input) {
        contact {
          id
          fields
          language {
            label
          }
        }
        errors {
          key
          message
        }
      }
    }
    """

    variables = {
        "id": glific_id,
        "input": update_payload
    }

    response = requests.post(url, json={"query": query, "variables": variables}, headers=headers)
    if response.status_code == 200:
        data = response.json()
        if "errors" in data:
            frappe.logger().error(f"Glific API Error: {data['errors']}")
            return False
        return True
    return False


# ! additonal code
def create_or_get_glific_contact(doc):
    # glific_contact = create_contact(
    #     doc.first_name,
    #     doc.phone_number,
    #     frappe.get_value("School", doc.school_id, "name1"),
    #     get_model_for_school(doc.school_id),
    #     frappe.get_value("TAP Language", doc.language, "glific_language_id")
    # )

    # if not glific_contact:
    #     glific_contact = get_contact_by_phone(doc.phone_number)

    # return glific_contact
    
    # First, try to get the existing contact by phone number
    glific_contact = get_contact_by_phone(doc.phone_number)

    if glific_contact:
        frappe.logger().info(f"Existing Glific contact found for phone number {doc.phone_number}")
        return glific_contact

    # If no existing contact is found, create a new one
    frappe.logger().info(f"No existing Glific contact found. Creating new contact for {doc.first_name} with phone {doc.phone_number}")
    glific_contact = create_contact(
        doc.first_name,
        doc.phone_number,
        frappe.get_value("School", doc.school_id, "name1"),
        get_model_for_school(doc.school_id),
        frappe.get_value("TAP Language", doc.language, "glific_language_id")
    )

    if glific_contact:
        frappe.logger().info(f"New Glific contact created successfully for {doc.first_name}")
    else:
        frappe.logger().error(f"Failed to create new Glific contact for {doc.first_name}")

    return glific_contact
