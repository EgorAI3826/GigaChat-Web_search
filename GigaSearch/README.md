# LAISer
## _Local AI-Assisted Web Search_

<img src="https://github.com/av1d/LAISer/blob/main/images/LAISer_logo.png" width="300" height="300" />

An experimental local search engine assistant frontend and CLI for [ollama](https://ollama.com/) and [llama.cpp](https://github.com/ggerganov/llama.cpp) with a focus on being extremely lightweight and easy to run. The goal is to provide something along the lines of a minimalist Perplexity. The web interface is responsive and works well with [mobile devices](https://github.com/av1d/LAISer/blob/main/images/screenshot_mobile.png).

Examples:
![Screenshot 01](https://github.com/av1d/LAISer/blob/main/images/screenshot_01.png)
![Screenshot 02](https://github.com/av1d/LAISer/blob/main/images/screenshot_02.png)
![Screenshot 03](https://github.com/av1d/LAISer/blob/main/images/screenshot_03.png)

It is written in Python 3 with [Flask](https://flask.palletsprojects.com/en/3.0.x/) which provides a web-based UI,
or you can run it from the command line instead.

If you can run [ollama](https://ollama.com/) or [llama.cpp](https://github.com/ggerganov/llama.cpp) then you can use this application.

It works by asking it a question or query like you would any other search engine.  
It provides citations for all articles it references.  
It does not chat, it only returns an answer.  

The functionality is rudimentary, naive and serves as a basic proof-of-concept to show that feeding search results into a model can enhance the quality of the search results without doing anything fancy.  

It will likely work with any halfway decent model but these are the ones I've tested it with. You don't really need anything fancy here. These are the tested models and they can be run on CPU (though may be a bit slow):

for llama.cpp:  
- [stablelm-zephyr-3b.Q4_K_M](https://huggingface.co/TheBloke/stablelm-zephyr-3b-GGUF)
- [rocket-3b.Q2_K.gguf](https://huggingface.co/TheBloke/rocket-3B-GGUF)
- [xwin-mlewd-7b-v0.2.Q2_K.gguf](https://huggingface.co/TheBloke/Xwin-MLewd-7B-V0.2-GGUF)
- [claude2-alpaca-7b.Q4_K_M.gguf](https://huggingface.co/TheBloke/claude2-alpaca-7B-GGUF)

for ollama:  
- stablelm-zephyr: `ollama pull stablelm-zephyr`
- solobsd/rocket-3b: `ollama pull solobsd/rocket-3b` * untested
- undi95/xwin-mlewd: `ollama pull undi95/xwin-mlewd` * untested

**Known issues & limitations:**
- It currently only supports one web request at a time.
- Doesn't allow refinement, it's "one and done".
- Doesn't work with Firefox mobile or desktop. Use literally any other browser instead.
- There are probably bugs.

**Install:**
```bash
git clone https://github.com/av1d/LAISer.git
cd LAISer
pip install -r requirements.txt
```  

**Run:**
- Make sure you have ollama or llama.cpp installed and running.
- Edit your settings in the file `settings.py` 

Now you can use it one of two ways:  
`python3 search.py -s` or `--server` for server mode, or:  
`python3 search.py -q "What is the cost of a new TV?"` or `--query` for command-line mode.  

Found it useful? [Tips](https://ko-fi.com/av1d_) appreciated but not required.
