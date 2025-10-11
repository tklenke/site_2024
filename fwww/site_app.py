# app.py or app/__init__.py
from flask import Flask, render_template, request, url_for, flash, redirect, \
                  jsonify, session
import time, os, json, queue, configparser
from src.llm_functions import FileProcessorThread
from src.site_functions import sanitize, new_question, new_revision, \
            get_process_info, set_process_info_key_value, url_from_source, \
            get_all_jobs_info, update_process_status, render_markdown_file
import markdown

INI_PATH = './site.ini'

app = Flask(__name__)

#give chromadb a little time to start
time.sleep(2)

### Load MiFrame Configuration
if not os.path.exists(INI_PATH):
    print(f"Can't find config file {INI_PATH}")
    exit()
cfg = configparser.ConfigParser()
cfg.read(INI_PATH)
app.debug = cfg.getboolean('LEVEL','DEBUG')
app.secret_key = cfg.get('KEYS','SESSION')
app.markdown_dir = cfg.get('PATHS','WWW_DiR')

FPQueue = queue.Queue()
FPThread = FileProcessorThread(cfg.get('PATHS','JOBS_DiR'), FPQueue, cfg.getboolean('RAG','USE_GPT'), \
                               cfg.get('KEYS','OPENAI'), cfg.get('HOSTS','CHROMA'), cfg.get('HOSTS','OLLAMA'))
FPThread.set_models(cfg.get('MODELS','EMBED'), cfg.get('MODELS','LLM_DRAFT'), cfg.get('MODELS','LLM_REVISE'))
FPThread.set_prompts(cfg.get('PROMPTS','PREFIX'), cfg.get('PROMPTS','INITIAL'), cfg.get('PROMPTS','SECONDARY'))
FPThread.set_docs_params(cfg.getfloat('RAG','MAX_DISTANCE'), cfg.getint('RAG','MIN_DOCUMENTS'), cfg.getint('RAG','MAX_DOCUMENTS'))

FPQueue.put("startup...checking all jobs")
Md = markdown.Markdown()

# ----------- Main Routes
@app.route("/")
def home():
    return show_markdown_page("home")

@app.route("/links")
def links():
    return show_markdown_page("links")

@app.route("/cozy")
def cozy_home():
    return show_markdown_page("cozy")

@app.route('/<string:md_file>/show')
def show_markdown_page(md_file):
    mdfilepath = os.path.join(app.markdown_dir,md_file+".md")
    if not os.path.exists(mdfilepath):
        flash(f"Requested page: {md_file} is invalid")
        return redirect(url_for('home'))
    return render_markdown_file(mdfilepath) 

# ---------- Cozy RAG and Search Functions
@app.route("/cozyrag")
def cozyrag_start():
    return render_template('cozyrag_start.html')

@app.route("/cozyrag/query", methods=('GET', 'POST'))
def cozyrag_query():
    session['process_id'] = None
    if request.method == 'POST':
        query = sanitize(request.form.get('question'))
        email = request.form.get('email')
        if not session.get('email') and email:
            email = sanitize(email)

        if not query:
            flash('Question is required.')
        elif len(query) > cfg.getint('RAG','MAX_QUERY_LEN'):
            flash(f"Questions limited to {cfg.getint('RAG','MAX_QUERY_LEN')} characters. Please rephrase.")
        elif email and len(email) > cfg.getint('RAG','MAX_INPUT_LEN'):
            flash("Email address malformed.")
        else:
            session['query'] = query
            if email:
                session['email'] = email
            return redirect(url_for('cozyrag_answer'))

    return render_template('cozyrag_query.html')

@app.route("/cozyrag/revise", methods=('GET', 'POST'))
def cozyrag_revise():
    session['process_id'] = new_revision(session['process_id'], cfg.get('PATHS','JOBS_DiR'), cfg.getint('RAG','PROCESS_ID_LEN'))
    FPQueue.put(session['process_id'])
    return redirect(url_for('cozyrag_answer'))

@app.route("/cozyrag/followup", methods=('GET', 'POST'))
def cozyrag_followup():
    if request.method == 'POST':
        query = sanitize(request.form.get('question'))

        if not query:
            flash('Question is required.')
        elif len(query) > cfg.getint('RAG','MAX_QUERY_LEN'):
            flash(f"Questions limited to {cfg.getint('RAG','MAX_QUERY_LEN')} characters. Please rephrase.")
        else:
            session['process_id'] = new_revision(session['process_id'], cfg.get('PATHS','JOBS_DiR'), \
                                              cfg.getint('RAG','PROCESS_ID_LEN'),query)
            FPQueue.put(session['process_id'])
            return redirect(url_for('cozyrag_answer'))

    return render_template('cozyrag_query.html')

@app.route("/cozyrag/answer", methods=('GET', 'POST'))
def cozyrag_answer():
    if session['process_id'] is None:
        processInput = {}
        processInput['query'] = session['query']
        processInput['email'] = session.get('email')
        session['process_id'] = new_question(processInput, cfg.get('PATHS','JOBS_DiR'), cfg.getint('RAG','PROCESS_ID_LEN'))
        FPQueue.put(session['process_id'])
    #return render_template('cozyrag_answer.html', user_input=processInput)
    return render_template('cozyrag_answer.html')

@app.route("/cozyrag/<string:process_id>/status")
def cozyrag_status(process_id):
    data = get_process_info(cfg.get('PATHS','JOBS_DiR'), process_id)
    cur_time = time.time() - data['created'] 

    if data['status'] == 'complete':
        data['result_html'] = render_template('cozyrag_results.html', results=data, show_revise=cfg.getboolean('OPTIONS','SHOW_REVISE'))
    else:
        data['status_text'] = "Status: " + data['status'] + "." * (int(cur_time) % 10)
    return jsonify(data)

@app.route("/cozyrag/feedback", methods=('GET', 'POST'))
def cozyrag_feedback():
    satisfaction = request.form.get("satisfaction")
    flash(f"Thank you for the feedback that the last response was {satisfaction}")
    set_process_info_key_value('satisfaction',satisfaction,cfg.get('PATHS','JOBS_DiR'), session['process_id'])
    return redirect(url_for('cozyrag_query'))

@app.route("/cozyrag/<string:process_id>/processid")
def cozyrag_processid(process_id):
    data = get_process_info(cfg.get('PATHS','JOBS_DiR'), process_id)
    return render_template('cozyrag_results.html', results=data, show_revise=cfg.getboolean('OPTIONS','SHOW_REVISE'))

@app.route("/cozyrag/jobs")
@app.route("/cozyrag/jobs/<column>")
def cozyrag_jobs(column=None):
    aJobsInfo = get_all_jobs_info(cfg.get('PATHS','JOBS_DiR'))

    # optional: validate column name
    valid_columns = {
        "email", "tokens_in", "tokens_out", "elapsed",
        "num_docs", "avg_score", "satisfaction", "query", "answer"
    }
    if column and column not in valid_columns:
        abort(404)

    return render_template(
        'cozyrag_jobs.html',
        jobs=aJobsInfo,
        column=column
    )


# ------ Context Processor for use in templates
@app.context_processor
def originid_anchor_processor():
    def originid_anchor(txt):
        href, click_txt = url_from_source(txt)
        return f"<a href='{href}'>{click_txt}</a>"
    return dict(originid_anchor=originid_anchor)

@app.context_processor
def markdown_to_html_processor():
    def markdown_to_html(mdtxt):
        return Md.convert(mdtxt)
    return dict(markdown_to_html=markdown_to_html)

# Define a custom truncate filter
@app.context_processor
def safe_truncate_processor():
    def safe_truncate(text, length=100):
        if text is None:
            return ''  # Return an empty string if text is None
        return text[:length] + '...' if len(text) > length else text
    return dict(safe_truncate=safe_truncate)

if __name__ == "__main__":
   app.run(host='0.0.0.0')
