import React, { useState, useRef } from 'react';
import axios from 'axios';
import './index.css';

function App() {
    const [textInput, setTextInput] = useState('');
    const [wsdlFile, setWsdlFile] = useState(null);
    const [generatedXml, setGeneratedXml] = useState('<!-- Generated XML will appear here -->');
    const [isLoading, setIsLoading] = useState(false);
    const fileInputRef = useRef(null);

    const handleAreaClick = () => {
        fileInputRef.current.click();
    };

    const handleFileChange = (e) => {
        setWsdlFile(e.target.files[0]);
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!wsdlFile) {
            alert('Please upload a WSDL file.');
            return;
        }

        setIsLoading(true);
        const formData = new FormData();
        formData.append('wsdl_file', wsdlFile);
        formData.append('user_input', textInput);

        try {
            const response = await axios.post('http://localhost:8000/generate-soapui-project/', formData, {
                headers: {
                    'Content-Type': 'multipart/form-data',
                },
            });
            setGeneratedXml(response.data);
        } catch (error) {
            console.error('Error generating SoapUI project:', error);
            setGeneratedXml('<!-- Error generating XML. Please check the console. -->');
        } finally {
            setIsLoading(false);
        }
    };

    const handleDownload = () => {
        const blob = new Blob([generatedXml], { type: 'application/xml' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'soapui-project.xml';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    };

    return (
        <div className="container mx-auto p-8">
            <header className="flex justify-between items-center mb-12">
                <div className="flex items-center gap-3">
                    <div className="bg-blue-600 text-white font-bold text-xl rounded-lg w-9 h-9 flex items-center justify-center">S</div>
                    <h1 className="text-xl font-semibold text-gray-800">SOAP Test Generator</h1>
                </div>
                <button className="flex items-center gap-2 border border-gray-300 rounded-full px-4 py-2 text-sm font-medium text-gray-800 hover:bg-gray-50">
                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"></circle><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"></path><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
                    <span>Help</span>
                </button>
            </header>

            <main>
                <section className="text-center mb-12">
                    <h2 className="text-4xl font-bold mb-3">Generate SOAP UI Tests with Ease</h2>
                    <p className="text-lg text-gray-500 max-w-2xl mx-auto">Provide your text input and WSDL file to automatically generate test cases.</p>
                </section>

                <section className="grid grid-cols-1 md:grid-cols-2 gap-8">
                    <div className="input-panel">
                        <form onSubmit={handleSubmit}>
                            <div className="form-group mb-6">
                                <label htmlFor="text-input" className="block font-medium text-sm mb-2">Text Input</label>
                                <textarea id="text-input" className="w-full h-36 p-3 border border-gray-300 rounded-lg focus:ring-blue-500 focus:border-blue-500" placeholder="Describe the test case in plain text..." value={textInput} onChange={(e) => setTextInput(e.target.value)}></textarea>
                            </div>
                            <div className="form-group mb-6">
                                <label htmlFor="wsdl-file" className="block font-medium text-sm mb-2">WSDL File</label>
                                <div className="file-drop-area relative flex flex-col justify-center items-center p-8 border-2 border-dashed border-gray-300 rounded-lg text-center cursor-pointer hover:border-blue-500 hover:bg-gray-50" onClick={handleAreaClick}>
                                    <div className="stitch-badge absolute -top-3 left-4 bg-gray-700 text-white px-3 py-1 rounded-full text-xs font-medium">Stitch - Design with AI</div>
                                    <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#6B7280" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>
                                    <p className="upload-text text-gray-500 mt-4"><strong className="text-blue-600 font-medium">Upload a file</strong> or drag and drop</p>
                                    <p className="upload-hint text-gray-400 text-sm mt-1">WSDL up to 10MB</p>
                                    <input type="file" id="wsdl-file-input" className="hidden" onChange={handleFileChange} ref={fileInputRef} />
                                </div>
                            </div>
                            <button type="submit" className="btn-primary w-full inline-flex items-center justify-center gap-2 px-6 py-3.5 text-base font-semibold text-white bg-blue-600 rounded-lg hover:bg-blue-700" disabled={isLoading}>
                                {isLoading ? 'Generating...' : (
                                    <>
                                        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>
                                        <span>Generate Tests</span>
                                    </>
                                )}
                            </button>
                        </form>
                    </div>

                    <div className="output-panel">
                        <div className="output-header flex justify-between items-center mb-2">
                            <label className="font-medium text-sm">Generated XML Test Code</label>
                            <button className="btn-download inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-800 bg-white border border-gray-300 rounded-lg hover:bg-gray-50" onClick={handleDownload}>
                                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                                <span>Download</span>
                            </button>
                        </div>
                        <div className="code-display w-full h-full min-h-[420px] bg-gray-100 border border-gray-300 rounded-lg p-4 overflow-auto">
                            <pre><code className="font-mono text-sm text-gray-500">{generatedXml}</code></pre>
                        </div>
                    </div>
                </section>
            </main>

            <footer className="text-center mt-16 pt-8 border-t border-gray-200">
                <p className="text-gray-500 text-sm">© 2024 SOAP Test Generator. All rights reserved.</p>
            </footer>
        </div>
    );
}

export default App;
