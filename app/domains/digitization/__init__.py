"""
Digitization domain: queues scanned documents/images, preprocesses them with OpenCV
on the backend and sends them to a pool of architects' PCs that only run the vision
model (Ollama + Qwen VL). The PCs are not dedicated, so any of them may be busy or
off at any time; the backend dispatcher only hands a job to a PC that answers.
"""
