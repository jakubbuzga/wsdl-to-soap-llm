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
        # Use a custom transport to load the WSDL from memory
        transport = Transport(cache=None)
        transport.load = lambda url: wsdl_content_bytes
        client = Client('dummy.wsdl', transport=transport)

        parsed_data = {"services": []}
        for service in client.wsdl.services.values():
            service_info = {"name": str(service.name), "ports": []}
            for port in service.ports.values():
                port_info = {"name": str(port.name), "binding": str(port.binding.name), "operations": []}
                for operation in port.binding._operations.values():
                    input_elements = []
                    if hasattr(operation.input, 'body') and hasattr(operation.input.body, 'parts'):
                        for part in operation.input.body.parts.values():
                            input_elements.append({"name": str(part.name), "type": str(part.type)})

                    output_elements = []
                    if hasattr(operation.output, 'body') and hasattr(operation.output.body, 'parts'):
                        for part in operation.output.body.parts.values():
                            output_elements.append({"name": str(part.name), "type": str(part.type)})

                    operation_info = {
                        "name": str(operation.name),
                        "input_elements": input_elements,
                        "output_elements": output_elements,
                    }
                    port_info["operations"].append(operation_info)
                service_info["ports"].append(port_info)
            parsed_data["services"].append(service_info)

        return {**state, "parsed_wsdl": parsed_data}
    except Exception as e:
        print(f"Error parsing WSDL: {e}")
        return {**state, "parsed_wsdl": {"error": str(e)}}

import requests
import json
import os

def generate_test_cases(state: GraphState) -> GraphState:
    """
    Generates example SOAP request bodies for each WSDL operation using an LLM.
    """
    print("---GENERATING TEST CASES---")
    parsed_wsdl = state.get("parsed_wsdl", {})
    user_input = state.get("user_input", "")
    ollama_base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

    generated_requests = {}

    for service in parsed_wsdl.get("services", []):
        for port in service.get("ports", []):
            for op in port.get("operations", []):
                op_name = op.get("name")
                prompt = f"""
                Given the following WSDL operation details, generate a JSON object containing three example SOAP request envelopes.
                The keys should be "positive_case", "negative_case", and "edge_case".
                The values should be the complete XML for a valid SOAP request envelope for that case.

                Operation: {op_name}
                Inputs: {json.dumps(op.get("input_elements", []), indent=2)}
                User Requirements: "{user_input}"

                Generate the full <soapenv:Envelope>...</soapenv:Envelope> for each case.
                Ensure the XML is well-formed.

                Example JSON Output format:
                {{
                    "positive_case": "<soapenv:Envelope ...>...</soapenv:Envelope>",
                    "negative_case": "<soapenv:Envelope ...>...</soapenv:Envelope>",
                    "edge_case": "<soapenv:Envelope ...>...</soapenv:Envelope>"
                }}
                """

                try:
                    response = requests.post(
                        f"{ollama_base_url}/api/generate",
                        json={
                            "model": "mistral",
                            "prompt": prompt,
                            "format": "json",
                            "stream": False
                        },
                        timeout=120
                    )
                    response.raise_for_status()
                    requests_str = response.json().get("response", "{}")
                    # The LLM response is a JSON string that needs to be parsed
                    generated_requests[op_name] = json.loads(requests_str)
                except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
                    print(f"Error generating test cases for operation {op_name}: {e}")
                    generated_requests[op_name] = {
                        "error_case": f"<error>Could not generate test case: {e}</error>"
                    }

    # The state now holds a dictionary of generated requests per operation
    return {**state, "test_cases": generated_requests}

from lxml import etree

def generate_soapui_xml(state: GraphState) -> GraphState:
    """
    Constructs a valid, self-contained SoapUI XML project file.
    """
    print("---GENERATING SOAPUI XML---")
    parsed_wsdl = state.get("parsed_wsdl", {})
    wsdl_content = state.get("wsdl_content", "")
    generated_requests = state.get("test_cases", {}) # Renamed for clarity

    # Define namespaces
    CON_NS = "http://eviware.com/soapui/config"
    XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
    NSMAP = {'con': CON_NS, 'xsi': XSI_NS}
    CON = f"{{{CON_NS}}}"

    # Create root element
    project = etree.Element(CON + "soapui-project", name="Generated LLM Project", soapui_version="5.7.0", nsmap=NSMAP)

    # Create WSDL Interface
    service = parsed_wsdl.get("services", [{}])[0]
    service_name = service.get("name", "MyService")
    port = service.get("ports", [{}])[0]
    binding_name = port.get("binding", "MyBinding")

    interface = etree.SubElement(project, CON + "interface",
        attrib={
            etree.QName(XSI_NS, "type"): "con:WsdlInterface",
            "name": binding_name,
            "type": "wsdl",
            "bindingName": binding_name,
            "soapVersion": "1_1", # Assuming 1.1 for now
            "wsaVersion": "NONE",
            "definition": "memory.wsdl" # Placeholder name
        }
    )

    # Embed the WSDL content
    definition_cache = etree.SubElement(interface, CON + "definitionCache", type="TEXT", rootPart="memory.wsdl")
    part = etree.SubElement(definition_cache, CON + "part")
    etree.SubElement(part, CON + "url").text = "memory.wsdl"
    etree.SubElement(part, CON + "content").text = etree.CDATA(wsdl_content)
    etree.SubElement(part, CON + "type").text = "http://schemas.xmlsoap.org/wsdl/"

    # Create Test Suite
    test_suite = etree.SubElement(project, CON + "testSuite", name=f"{service_name} TestSuite")

    # Create Test Cases and Steps for each operation
    for op_name, requests in generated_requests.items():
        test_case = etree.SubElement(test_suite, CON + "testCase", name=f"{op_name} TestCase")

        for case_type, request_xml in requests.items():
            test_step = etree.SubElement(test_case, CON + "testStep", type="request", name=f"{op_name} - {case_type}")

            config = etree.SubElement(test_step, CON + "config", attrib={etree.QName(XSI_NS, "type"): "con:RequestStep"})
            etree.SubElement(config, CON + "interface").text = binding_name
            etree.SubElement(config, CON + "operation").text = op_name

            request_elem = etree.SubElement(config, CON + "request")
            etree.SubElement(request_elem, CON + "request").text = etree.CDATA(request_xml)
            # Add default assertions
            assertions = etree.SubElement(request_elem, CON + "assertions")
            assertion_config = etree.SubElement(assertions, CON + "assertion", type="Valid HTTP Status Codes")
            etree.SubElement(assertion_config, CON + "configuration").text = "200"

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
