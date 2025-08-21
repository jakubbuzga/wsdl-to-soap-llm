from typing import TypedDict, List
from langgraph.graph import StatefulGraph, END

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
        wsdl_content = state["wsdl_content"].encode("utf-8")
        # Use a custom transport to load the WSDL from memory
        transport = Transport(cache=None)
        transport.load = lambda url: BytesIO(wsdl_content)
        client = Client(wsdl_content, transport=transport)

        parsed_data = {"services": []}
        for service in client.wsdl.services.values():
            service_info = {"name": service.name, "ports": []}
            for port in service.ports.values():
                port_info = {"name": port.name, "binding": port.binding.name, "operations": []}
                for operation in port.binding._operations.values():
                    operation_info = {
                        "name": operation.name,
                        "input_elements": [
                            {"name": part.name, "type": str(part.type)}
                            for part in operation.input.body.parts.values()
                        ],
                        "output_elements": [
                            {"name": part.name, "type": str(part.type)}
                            for part in operation.output.body.parts.values()
                        ],
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
    Generates test cases with assertions using the LLM.
    """
    print("---GENERATING TEST CASES---")
    parsed_wsdl = state["parsed_wsdl"]
    user_input = state["user_input"]

    # Get the Ollama base URL from environment variables
    ollama_base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

    prompt = f"""
    Based on the following WSDL information and user requirements, generate a list of test cases in JSON format.
    Each test case should have a 'name', 'request' body, and a list of 'assertions'.

    WSDL Info:
    {json.dumps(parsed_wsdl, indent=2)}

    User Requirements:
    {user_input}

    JSON Output format:
    [
        {{
            "name": "Test Case Name",
            "request": "<soapenv:Envelope ...>...</soapenv:Envelope>",
            "assertions": ["assertion1", "assertion2"]
        }}
    ]
    """

    try:
        response = requests.post(
            f"{ollama_base_url}/api/generate",
            json={
                "model": "mistral", # Or another model of your choice
                "prompt": prompt,
                "format": "json",
                "stream": False
            },
            timeout=120
        )
        response.raise_for_status()

        # The response from Ollama is a JSON string in the 'response' key
        test_cases_str = response.json().get("response", "[]")
        test_cases = json.loads(test_cases_str)

        return {**state, "test_cases": test_cases}
    except requests.exceptions.RequestException as e:
        print(f"Error calling LLM: {e}")
        return {**state, "test_cases": [{"name": "Error", "request": str(e), "assertions": []}]}
    except json.JSONDecodeError as e:
        print(f"Error parsing LLM response: {e}")
        return {**state, "test_cases": [{"name": "Error", "request": "Invalid JSON from LLM", "assertions": []}]}

from lxml import etree

def generate_soapui_xml(state: GraphState) -> GraphState:
    """
    Constructs the SoapUI XML project file from the generated test cases.
    """
    print("---GENERATING SOAPUI XML---")
    test_cases = state.get("test_cases", [])

    project = etree.Element("con:soapui-project", name="Generated Project", xmlns_con="http://eviware.com/soapui/config")

    for i, test_case in enumerate(test_cases):
        test_suite = etree.SubElement(project, "con:testSuite", name=f"TestSuite {i+1}")
        test_case_elem = etree.SubElement(test_suite, "con:testCase", name=test_case.get("name", f"TestCase {i+1}"))

        test_step = etree.SubElement(test_case_elem, "con:testStep", type="request", name=f"Request {i+1}")
        config = etree.SubElement(test_step, "con:config")
        etree.SubElement(config, "con:request", name=f"Request {i+1}").text = etree.CDATA(test_case.get("request", ""))

        assertions = etree.SubElement(test_step, "con:assertions")
        for assertion in test_case.get("assertions", []):
            etree.SubElement(assertions, "con:assertion", type="Valid HTTP Status Codes").text = "200"

    xml_content = etree.tostring(project, pretty_print=True, xml_declaration=True, encoding="UTF-8")
    return {**state, "soapui_project_xml": xml_content.decode("utf-8")}

# 3. Define the graph
def create_workflow():
    workflow = StatefulGraph(GraphState)

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
