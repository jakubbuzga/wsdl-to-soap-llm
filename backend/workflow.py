from typing import TypedDict, List
from langgraph.graph import StateGraph, END

# 1. Define the state for the graph
class GraphState(TypedDict):
    wsdl_content: str
    user_input: str
    parsed_wsdl: dict
    test_cases: List[dict]
    soapui_project_xml: str

# 2. Define the nodes for the graph
from zeep import Client
from zeep.transports import Transport
from io import BytesIO

def parse_wsdl(state: GraphState) -> GraphState:
    """
    Parses the WSDL file content to extract services, operations, and types.
    """
    print("---PARSING WSDL---")
    try:
        wsdl_content_bytes = state["wsdl_content"].encode("utf-8")
        transport = Transport(cache=None)
        transport.load = lambda url: wsdl_content_bytes
        client = Client('dummy.wsdl', transport=transport)

        def get_qname_parts(qname):
            """Extracts namespace and localname from a QName string like '{ns}name'."""
            if '}' in qname and qname.startswith('{'):
                ns, name = qname.split('}', 1)
                return ns[1:], name
            return None, qname

        target_namespace = None
        parsed_data = {"services": []}

        for service in client.wsdl.services.values():
            service_ns, service_name = get_qname_parts(service.name)
            service_info = {"name": service_name, "ports": []}

            for port in service.ports.values():
                port_ns, port_name = get_qname_parts(port.name)

                # Extract namespace from the binding qname
                binding_qname = port.binding.name
                binding_ns, binding_name = get_qname_parts(binding_qname)
                if binding_ns and not target_namespace:
                    target_namespace = binding_ns

                port_info = {"name": port_name, "binding": binding_name, "operations": []}
                for op_name, operation in port.binding._operations.items():
                    input_elements = []
                    if operation.input.body.parts:
                        part = list(operation.input.body.parts.values())[0]
                        element = part.element
                        if element and hasattr(element.type, 'elements'):
                            for elem_name, elem_type in element.type.elements:
                                input_elements.append({"name": elem_name, "type": elem_type.name})

                    operation_info = {
                        "name": op_name,
                        "soap_action": operation.soapaction,
                        "input_elements": input_elements,
                    }
                    port_info["operations"].append(operation_info)
                service_info["ports"].append(port_info)
            parsed_data["services"].append(service_info)

        # Add the extracted namespace to the final parsed data
        parsed_data["target_namespace"] = target_namespace or ""

        return {**state, "parsed_wsdl": parsed_data}
    except Exception as e:
        print(f"Error parsing WSDL: {e}")
        return {**state, "parsed_wsdl": {"error": str(e)}}

import requests
import json
import os

def generate_test_cases(state: GraphState) -> GraphState:
    """
    Generates test cases with requests and assertions for each WSDL operation using an LLM.
    """
    print("---GENERATING TEST CASES---")
    parsed_wsdl = state.get("parsed_wsdl", {})
    user_input = state.get("user_input", "")
    target_namespace = parsed_wsdl.get("target_namespace", "")
    ollama_base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

    all_test_cases = {}

    for service in parsed_wsdl.get("services", []):
        for port in service.get("ports", []):
            for op in port.get("operations", []):
                op_name = op.get("name")
                soap_action = op.get("soap_action")

                prompt = f"""
                You are a SoapUI test case generation expert.
                Given the WSDL operation details, generate a JSON object containing three test cases: a positive case, a negative case, and an edge case.

                **Operation Details:**
                - Name: {op_name}
                - Target Namespace: {target_namespace}
                - SOAP Action: {soap_action}
                - Input Elements: {json.dumps(op.get("input_elements", []), indent=2)}
                - User Requirements: "{user_input}"

                **Instructions:**
                1.  **Request Body:** Create a complete, well-formed SOAP 1.1 envelope for each test case.
                    - The request payload (inside soapenv:Body) must have its elements qualified with the target namespace: `xmlns="{target_namespace}"`.
                    - Use realistic and meaningful data.
                2.  **Test Case Name:** Provide a descriptive name for each test case.
                3.  **Assertions:** For each test case, provide a list of appropriate SoapUI assertions.
                    - For positive cases, include `Valid HTTP Status Codes` (200) and an `XPath Match` to verify a key element in the response.
                    - For negative cases, expect a SOAP Fault. Assertions should be `SOAP Fault` and `Valid HTTP Status Codes` (500).
                    - For edge cases, assertions will depend on the case, but should at least include `Valid HTTP Status Codes` (200).

                **JSON Output Format:**
                {{
                  "positive_case": {{
                    "name": "Descriptive name for the positive test",
                    "request": "<soapenv:Envelope ...>...</soapenv:Envelope>",
                    "assertions": [
                      {{"type": "Valid HTTP Status Codes", "value": "200"}},
                      {{"type": "XPath Match", "value": "/*:Envelope/*:Body/*:YourResponseElement/*:SomeField"}}
                    ]
                  }},
                  "negative_case": {{
                    "name": "Descriptive name for the negative test",
                    "request": "<soapenv:Envelope ...>...</soapenv:Envelope>",
                    "assertions": [
                      {{"type": "SOAP Fault", "value": ""}},
                      {{"type": "Valid HTTP Status Codes", "value": "500"}}
                    ]
                  }},
                  "edge_case": {{
                    "name": "Descriptive name for the edge case",
                    "request": "<soapenv:Envelope ...>...</soapenv:Envelope>",
                    "assertions": [
                      {{"type": "Valid HTTP Status Codes", "value": "200"}}
                    ]
                  }}
                }}
                """

                try:
                    print(f"Generating test cases for operation: {op_name}")
                    response = requests.post(
                        f"{ollama_base_url}/api/generate",
                        json={"model": "mistral", "prompt": prompt, "format": "json", "stream": False},
                        timeout=180
                    )
                    response.raise_for_status()
                    response_json_str = response.json().get("response", "{}")

                    # The LLM often returns a markdown block ```json ... ```, so we need to strip it
                    if response_json_str.startswith("```json"):
                        response_json_str = response_json_str[7:-4].strip()

                    test_case_data = json.loads(response_json_str)
                    all_test_cases[op_name] = test_case_data
                except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
                    print(f"Error generating test cases for operation {op_name}: {e}")
                    # Provide a fallback error structure
                    all_test_cases[op_name] = {
                        "error_case": {
                            "name": f"Error Generating Case for {op_name}",
                            "request": f"<error>Could not generate test case: {e}</error>",
                            "assertions": []
                        }
                    }

    return {**state, "test_cases": all_test_cases}

from lxml import etree

def generate_soapui_xml(state: GraphState) -> GraphState:
    """
    Constructs a valid, self-contained SoapUI XML project file from the generated test cases.
    """
    print("---GENERATING SOAPUI XML---")
    parsed_wsdl = state.get("parsed_wsdl", {})
    wsdl_content = state.get("wsdl_content", "")
    all_test_cases = state.get("test_cases", {})

    CON_NS = "http://eviware.com/soapui/config"
    XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
    NSMAP = {'con': CON_NS, 'xsi': XSI_NS}
    CON = f"{{{CON_NS}}}"

    service = parsed_wsdl.get("services", [{}])[0]
    service_name = service.get("name", "MyService")
    project_name = f"{service_name} LLM Project"

    project = etree.Element(CON + "soapui-project", name=project_name, soapui_version="5.7.0", nsmap=NSMAP)

    port = service.get("ports", [{}])[0]
    binding_name = port.get("binding", "MyBinding")

    interface = etree.SubElement(project, CON + "interface",
        attrib={
            etree.QName(XSI_NS, "type"): "con:WsdlInterface",
            "name": binding_name, "type": "wsdl", "bindingName": binding_name,
            "soapVersion": "1_1", "wsaVersion": "NONE", "definition": "memory.wsdl"
        }
    )

    definition_cache = etree.SubElement(interface, CON + "definitionCache", type="TEXT", rootPart="memory.wsdl")
    part = etree.SubElement(definition_cache, CON + "part")
    etree.SubElement(part, CON + "url").text = "memory.wsdl"
    etree.SubElement(part, CON + "content").text = etree.CDATA(wsdl_content)
    etree.SubElement(part, CON + "type").text = "http://schemas.xmlsoap.org/wsdl/"

    test_suite = etree.SubElement(project, CON + "testSuite", name=f"{service_name} TestSuite")

    for op_name, cases in all_test_cases.items():
        test_case_name = f"{op_name} TestCase"
        test_case = etree.SubElement(test_suite, CON + "testCase", name=test_case_name)

        for case_type, case_data in cases.items():
            test_step_name = case_data.get("name", f"{op_name} - {case_type}")
            test_step = etree.SubElement(test_case, CON + "testStep", type="request", name=test_step_name)

            config = etree.SubElement(test_step, CON + "config", attrib={etree.QName(XSI_NS, "type"): "con:RequestStep"})
            etree.SubElement(config, CON + "interface").text = binding_name
            etree.SubElement(config, CON + "operation").text = op_name

            request_elem = etree.SubElement(config, CON + "request")
            etree.SubElement(request_elem, CON + "request").text = etree.CDATA(case_data.get("request", ""))

            assertions_elem = etree.SubElement(request_elem, CON + "assertions")
            for assertion in case_data.get("assertions", []):
                assertion_type = assertion.get("type")
                assertion_value = assertion.get("value")

                if not assertion_type:
                    continue

                assertion_config = etree.SubElement(assertions_elem, CON + "assertion", type=assertion_type)
                config_elem = etree.SubElement(assertion_config, CON + "configuration")

                if assertion_type == "Valid HTTP Status Codes":
                    etree.SubElement(config_elem, CON + "codes").text = str(assertion_value)
                elif assertion_type == "XPath Match":
                    etree.SubElement(config_elem, CON + "path").text = str(assertion_value)
                    etree.SubElement(config_elem, CON + "content").text = "true" # Default to check for existence
                    etree.SubElement(config_elem, CON + "allowWildcards").text = "true"
                    etree.SubElement(config_elem, CON + "ignoreNamspaceDifferences").text = "true"
                    etree.SubElement(config_elem, CON + "ignoreComments").text = "true"
                # For SOAP Fault, Not SOAP Fault, etc., no extra config is needed

    xml_content = etree.tostring(project, pretty_print=True, xml_declaration=True, encoding="UTF-8")
    return {**state, "soapui_project_xml": xml_content.decode("utf-8")}

# 3. Define the graph
def create_workflow():
    workflow = StateGraph(GraphState)

    # Add the nodes
    workflow.add_node("parse_wsdl", parse_wsdl)
    workflow.add_node("generate_test_cases", generate_test_cases)
    workflow.add_node("generate_soapui_xml", generate_soapui_xml)

    # Set the entrypoint
    workflow.set_entry_point("parse_wsdl")

    # Add edges
    workflow.add_edge("parse_wsdl", "generate_test_cases")
    workflow.add_edge("generate_test_cases", "generate_soapui_xml")
    workflow.add_edge("generate_soapui_xml", END)

    # Compile the graph
    return workflow.compile()
