# app.py or app/__init__.py
from flask import Flask, render_template, request, url_for, flash, redirect, \
                  jsonify, session
import time, os, json, queue
from src.llm_functions import FileProcessorThread
from src.site_functions import sanitize, new_question, get_process_info

app = Flask(__name__)

app.config.from_object('config')
# Now we can access the configuration variables via app.config["VAR_NAME"].
app.config["DEBUG"]
#TODO get this from OS or Config. Maybe use same shell script that makes OPENAI key.
app.config['SECRET_KEY'] = 'mysecretkey123321'
app.config['MAX_QUERY_LEN'] = 512
app.config['MAX_INPUT_LEN'] = 75
app.config['JOBS_DiR'] = '/app/jobs'
app.config['PROCESS_ID_LEN'] = 10
FPQueue = queue.Queue()
FPThread = FileProcessorThread(app.config['JOBS_DiR'],FPQueue)
FPQueue.put("startup...checking all jobs")

# ----------- Main Routes
@app.route("/")
def home():
    return render_template('home.html')

@app.route("/cozy")
def cozy_home():
    return render_template('cozy_home.html')

# ---------- Cozy RAG and Search Functions
@app.route("/cozyrag")
def cozyrag_start():
    return render_template('cozyrag_start.html')

@app.route("/cozyrag/query", methods=('GET', 'POST'))
def cozyrag_query():
    if request.method == 'POST':
        query = sanitize(request.form.get('question'))
        email = request.form.get('email')
        if not session.get('email') and email:
            email = sanitize(email)

        if not query:
            flash('Question is required.')
        elif len(query) > app.config['MAX_QUERY_LEN']:
            flash(f"Questions limited to {app.config['MAX_QUERY_LEN']} characters. Please rephrase.")
        elif email and len(email) > app.config['MAX_INPUT_LEN']:
            flash("Email address malformed.")
        else:
            session['query'] = query
            if email:
                session['email'] = email
            return redirect(url_for('cozyrag_answer'))

    return render_template('cozyrag_query.html')

@app.route("/cozyrag/answer", methods=('GET', 'POST'))
def cozyrag_answer():
    processInput = {}
    processInput['query'] = session['query']
    processInput['email'] = session.get('email')
    session['process_id'] = new_question(processInput, app.config['JOBS_DiR'], app.config['PROCESS_ID_LEN'])
    FPQueue.put(session['process_id'])
    return render_template('cozyrag_answer.html', user_input=processInput)

@app.route("/cozyrag/<string:process_id>/status")
def cozyrag_status(process_id):
    data = get_process_info(app.config['JOBS_DiR'], process_id)
    elapsed = time.time() - float(data['created'])
    data['elapsed'] = elapsed

    if data['status'] == 'complete':
        data['result_html'] = render_template('cozyrag_results.html', results=data)
    else:
        data['status_text'] = "Status: " + data['status'] + "." * (int(elapsed) % 10)
    return jsonify(data)

if __name__ == "__main__":
   app.run(host='0.0.0.0')