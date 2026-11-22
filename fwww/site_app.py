# app.py or app/__init__.py
from flask import Flask, render_template, request, url_for, flash, redirect, \
                  jsonify, session, abort
import time, os, json, queue
from src.llm_functions import FileProcessorThread
from src.site_config import read_config
from src.site_functions import new_question, new_revision, \
            get_process_info, set_process_info_key_value, url_from_source, \
            get_all_jobs_info, get_job_for_display, update_process_status, \
            render_markdown_file
import markdown

FEEDBACK_RATINGS = ('perfect', 'ok', 'not_good')

app = Flask(__name__)

#give chromadb a little time to start
time.sleep(2)

### Load MiFrame Configuration
cfg = read_config('.')
app.debug = cfg.getboolean('LEVEL','DEBUG')
app.secret_key = cfg.get('KEYS','SESSION')
app.markdown_dir = cfg.get('PATHS','WWW_DiR')

FPQueue = queue.Queue()
FPThread = FileProcessorThread(cfg.get('PATHS','JOBS_DiR'), FPQueue, cfg.getboolean('RAG','USE_GPT'), \
                               cfg.get('KEYS','OPENAI'), cfg.get('HOSTS','CHROMA'), cfg.get('HOSTS','OLLAMA'))
FPThread.set_models(cfg.get('MODELS','EMBED'), cfg.get('MODELS','LLM_DRAFT'), cfg.get('MODELS','LLM_REVISE'))
FPThread.set_embed_prefix(cfg.get('PROMPTS','PREFIX'))
FPThread.set_docs_params(cfg.getfloat('RAG','MAX_DISTANCE'), cfg.getint('RAG','MIN_DOCUMENTS'), \
                         cfg.getint('RAG','MAX_DOCUMENTS'), cfg.getint('RAG','MAX_DRAFT_DOCUMENTS'),)

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
        query = request.form.get('question')
        email = request.form.get('email')

        if not query:
            flash('Question is required.')
        elif len(query) > cfg.getint('RAG','MAX_QUERY_LEN'):
            flash(f"Questions limited to {cfg.getint('RAG','MAX_QUERY_LEN')} characters. Please rephrase.")
        elif email and len(email) > cfg.getint('RAG','MAX_INPUT_LEN'):
            flash("Email address malformed.")
        else:
            if email:
                session['email'] = email
            processInput = {}
            processInput['query'] = query
            processInput['email'] = session.get('email')
            session['process_id'] = new_question(processInput, cfg.get('PATHS','JOBS_DiR'), cfg.getint('RAG','PROCESS_ID_LEN'))
            FPQueue.put(session['process_id'])
            return redirect(url_for('cozyrag_answer'))

    return render_template('cozyrag_query.html')

# only a job with an answer can be revised or followed up
def has_answer(process_id):
    return bool(get_process_info(cfg.get('PATHS','JOBS_DiR'), process_id).get('result'))

@app.route("/cozyrag/revise", methods=('POST',))
def cozyrag_revise():
    if not session.get('process_id') or not has_answer(session['process_id']):
        return redirect(url_for('cozyrag_query'))
    session['process_id'] = new_revision(session['process_id'], cfg.get('PATHS','JOBS_DiR'), cfg.getint('RAG','PROCESS_ID_LEN'))
    FPQueue.put(session['process_id'])
    return redirect(url_for('cozyrag_answer'))

@app.route("/cozyrag/followup", methods=('GET', 'POST'))
def cozyrag_followup():
    if not session.get('process_id'):
        return redirect(url_for('cozyrag_query'))
    if request.method == 'POST':
        query = request.form.get('question')

        if not query:
            flash('Question is required.')
        elif len(query) > cfg.getint('RAG','MAX_QUERY_LEN'):
            flash(f"Questions limited to {cfg.getint('RAG','MAX_QUERY_LEN')} characters. Please rephrase.")
        elif not has_answer(session['process_id']):
            return redirect(url_for('cozyrag_query'))
        else:
            session['process_id'] = new_revision(session['process_id'], cfg.get('PATHS','JOBS_DiR'), \
                                              cfg.getint('RAG','PROCESS_ID_LEN'),query)
            FPQueue.put(session['process_id'])
            return redirect(url_for('cozyrag_answer'))

    return render_template('cozyrag_query.html')

@app.route("/cozyrag/answer", methods=('GET', 'POST'))
def cozyrag_answer():
    if not session.get('process_id'):
        return redirect(url_for('cozyrag_query'))
    #return render_template('cozyrag_answer.html', user_input=processInput)
    return render_template('cozyrag_answer.html')

@app.route("/cozyrag/<string:process_id>/status")
def cozyrag_status(process_id):
    data = get_process_info(cfg.get('PATHS','JOBS_DiR'), process_id)
    if not data:
        abort(404)
    cur_time = time.time() - data['created'] 

    status = {'status': data['status']}
    if data['status'] == 'complete':
        status['result_html'] = render_template('cozyrag_results.html', results=get_job_for_display(data), show_revise=cfg.getboolean('OPTIONS','SHOW_REVISE'))
    else:
        status['status_text'] = "Status: " + data['status'] + "." * (int(cur_time) % 10)
    return jsonify(status)

@app.route("/cozyrag/feedback", methods=('GET', 'POST'))
def cozyrag_feedback():
    satisfaction = request.form.get("satisfaction")
    if not session.get('process_id') or satisfaction not in FEEDBACK_RATINGS:
        return redirect(url_for('cozyrag_query'))
    flash(f"Thank you for the feedback that the last response was {satisfaction}")
    set_process_info_key_value('satisfaction',satisfaction,cfg.get('PATHS','JOBS_DiR'), session['process_id'])
    return redirect(url_for('cozyrag_query'))

@app.route("/cozyrag/<string:process_id>/processid")
def cozyrag_processid(process_id):
    data = get_job_for_display(get_process_info(cfg.get('PATHS','JOBS_DiR'), process_id))
    #an unknown or unfinished job has no results to show
    if not data['result']:
        abort(404)
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

if __name__ == "__main__":
   app.run(host='0.0.0.0')
