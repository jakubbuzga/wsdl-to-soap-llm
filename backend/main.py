from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import io
from workflow import create_workflow

app = FastAPI()

origins = [
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

workflow = create_workflow()

@app.post("/generate-soapui-project/")
async def generate_soapui_project(
    wsdl_file: UploadFile = File(...),
    user_input: str = Form(...)
):
    """
    This endpoint generates a SoapUI project from a WSDL file and user input.
    """
    wsdl_content = await wsdl_file.read()

    initial_state = {
        "wsdl_content": wsdl_content.decode("utf-8"),
        "user_input": user_input
    }

    final_state = workflow.invoke(initial_state)

    soapui_project_xml = final_state.get("soapui_project_xml", "<error>No XML generated</error>")

    return StreamingResponse(
        io.BytesIO(soapui_project_xml.encode("utf-8")),
        media_type="application/xml",
        headers={"Content-Disposition": "attachment; filename=soapui-project.xml"}
    )
