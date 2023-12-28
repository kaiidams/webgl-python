# WebGL over WebSocket from Python

A Python web server that controls WebGL of the browser.
You can call WebGL API of a web browser that supports the API from a remote Python script.

# Run

Start the server.

```sh
pip install -r requrements.txt
uvicorn main:app
```

Open the URL from your browser. Chrome or Firefox for both desktop or mobile should work.
Then run the demo Python script.

```sh
python test.py
```

![screenshot](screenshot.png)