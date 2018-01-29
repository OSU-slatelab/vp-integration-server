from flask import Flask, request, redirect, url_for, Response, abort
from flask_mysqldb import MySQL
from flask_cors import CORS
from werkzeug.utils import secure_filename

import vpcnn.model
import vpcnn.vpdataset 
import vpcnn.train
import torchtext.data as data
import torch.autograd as autograd
import torch

from collections import namedtuple
import socket
import json
import glob
import os
import pkg_resources
import re
import random
from math import log10
from scipy.stats import entropy

from gevent.pywsgi import WSGIServer
from gevent import monkey
from gevent import signal

from cs_cnn_choose import *

import logging
from logging.handlers import RotatingFileHandler


monkey.patch_all()

WS_VERSION = "1.1.0"
CNN_Args = namedtuple('CNN_Args', ['embed_num',
                                   'char_embed_dim',
                                   'word_embed_dim',
                                   'class_num',
                                   'kernel_num',
                                   'char_kernel_sizes',
                                   'word_kernel_sizes',
                                   'ortho_init',
                                   'dropout',
                                   'static',
                                   'word_vector'])

Predict_Args = namedtuple('Predict_Args', ['ensemble', 'cuda'])
                                           
with open('config.json') as conf_json:
    conf = json.load(conf_json)


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
rfh = RotatingFileHandler(conf['log_file'],
                          maxBytes=100000,
                          backupCount=2,
                          encoding="UTF-8")
logger.addHandler(rfh)

cs_host = conf['cs_host'] 
cs_port = conf['cs_port'] 
cs_bufsize = conf['cs_bufsize'] 

app = Flask(__name__)
app.config['MYSQL_USER'] = conf['db_user']
app.config['MYSQL_PASSWORD'] = conf['db_pass']
app.config['MYSQL_DB'] = conf['db_db']
app.config['MYSQL_HOST'] = conf['db_host']
db = MySQL(app)
app.config['MAX_CONTENT_LENGTH'] = 9999999
CORS(app)

logger.info("Building vocabularies...")
word_tokenizer = data.Pipeline(vpcnn.vpdataset.clean_str)
char_field = data.Field(lower=True, tokenize=lambda x: list(x))
word_field = data.Field(lower=True, tokenize=word_tokenizer, batch_first=True)
label_field = data.Field(sequential=False, use_vocab=False, preprocessing=int)

label_map_fn = pkg_resources.resource_filename('vpcnn', 'data/labels.txt')
idx_to_lbl = []
lbl_to_idx = {}
with open(label_map_fn) as f:
    for line in f.readlines():
        lbl, text = line.strip().split('\t')
        idx_to_lbl.insert(int(lbl), text)
        lbl_to_idx[text] = int(lbl)

extract_interp_re = re.compile(r'[us\?]:\s+\S+\s+\((.*?)\)')
        
char_train_data, char_dev_data, char_test_data = vpcnn.vpdataset.VP.splits(char_field,
                                                                           label_field,
                                                                           foldid = 1,
                                                                           num_experts = 5)
char_field.build_vocab(char_train_data[0],
                       char_dev_data[0],
                       char_test_data,
                       wv_type=None,
                       wv_dim=None,
                       wv_dir=None,
                       min_freq=1)
word_train_data, word_dev_data, word_test_data = vpcnn.vpdataset.VP.splits(word_field,
                                                                           label_field,
                                                                           foldid = 1,
                                                                           num_experts = 5)
word_field.build_vocab(word_train_data[0],
                       word_dev_data[0],
                       word_test_data,
                       wv_type=None, 
                       wv_dim=None, 
                       wv_dir=None, 
                       min_freq=1)
logger.info("Done.")
logger.info("Loading character CNN models...")
char_args = CNN_Args(embed_num = len(char_field.vocab),
                     char_embed_dim = 16,
                     word_embed_dim = 300,
                     class_num = 359,
                     kernel_num = 400,
                     char_kernel_sizes = [2,3,4,5,6],
                     word_kernel_sizes = [3,4,5],
                     ortho_init = False,
                     dropout = 0.5,
                     static = False,
                     word_vector = 'w2v')
char_mdl_path = os.path.join(conf['char_cnn_dir'], '*')
char_mdl_files = glob.glob(char_mdl_path)
char_mdls = []
for i in range(len(char_mdl_files)):
    char_mdls.append(vpcnn.model.CNN_Text(char_args, 'char'))
    char_mdls[i].load_state_dict(torch.load(char_mdl_files[i], map_location= lambda stor, loc: stor))

logger.info("Loading word CNN models...")
logger.info("Vocab size: %d", len(word_field.vocab))
word_args = CNN_Args(embed_num = len(word_field.vocab), ## (should be 1715)
                     char_embed_dim = 16,
                     word_embed_dim = 300,
                     class_num = 359,
                     kernel_num = 300,
                     char_kernel_sizes = [2,3,4,5,6],
                     word_kernel_sizes = [3,4,5],
                     ortho_init = False,
                     dropout = 0.5,
                     static = False,
                     word_vector = 'w2v')
word_mdl_path = os.path.join(conf['word_cnn_dir'], '*')
word_mdl_files = glob.glob(word_mdl_path)
word_mdls = []
for i in range(len(word_mdl_files)):
    word_mdls.append(vpcnn.model.CNN_Text(word_args, 'word'))
    word_mdls[i].load_state_dict(torch.load(word_mdl_files[i], map_location= lambda stor, loc: stor))

logger.info("Loading word/char binary classifier...")
choose_mdl_path = os.path.join(conf['choose_cnn_dir'], 'final_model.0.pt')
choose_mdl = vpcnn.model.StackingNet(None)
choose_mdl.load_state_dict(torch.load(choose_mdl_path, map_location= lambda stor, loc: stor))
    
logger.info("Done.")

decider = CS_CNN_chooser(conf['cs_cnn_classifier'], conf['cs_cnn_vectorizer'])

def cnn_predict(query):
    predicted_query = ""
    args = Predict_Args(ensemble = 'vot', cuda = False)
    # preprocess query
    char_in = char_field.preprocess(query)
    x1 = char_field.numericalize(char_in, device=-1, train=False)
    word_in = word_field.preprocess(query)
    x2 = word_field.numericalize([word_in], device=-1, train=False)
    # run models
    char_out, (char_conf, _, _) = vpcnn.train.ensemble_predict((x1, -1), char_mdls, args)
    word_out, (word_conf, _, _) = vpcnn.train.ensemble_predict((x2, -1), word_mdls, args)
    class_prob = choose_mdl((char_out, word_out))
    class_conf = char_conf + word_conf
    return class_prob, class_conf

def best_idx(tensor):
    # postprocess output
    _, argmax = torch.max(tensor, 1)
    idx = int(argmax.data[0])
    # print(label_map[int(argmax.data[0])])
    return idx

def query(class_num):
    return idx_to_lbl[class_num]

def class_num(query):
    return lbl_to_idx[query]

#def entropy(tensor):
#    return

def process_vars(line):
    mvars = {"chiefcomplaint":"pain",
             "complaint2":"frequent urination",
             "patientname":"wilkins",
             "patientlastname":"wilkins",
             "currentmedication1":"ibuprofen",
             "currentjob":"mechanic",
             "patientfirstname":"jim"}
    if "$" not in line:
        return line
    else:
        assignments = re.findall(r'\$[a-zA-Z0-9]+\?',line)
        for assignment in assignments:
            varname = assignment[1:-1]
            #placeholder = assignment.split("=")[1]
            ##for each occurrence of placeholder in line, replace with varname lookup
            try:
                varvalue = mvars[varname]
            except KeyError:
                varvalue = varname
            line = re.sub(" "+re.escape(assignment)+" "," "+varvalue+" ", line)
            # line = line.split("$")[0] #cut at first variable assignment
        return line
                                                                                            
## TODO? Might make more sense to grab the template name instead of the match
def process_match(why):
    logger.debug(why)
    match = extract_interp_re.search(why)
    if match:
        raw = match.group(1).strip()
        processed = process_vars(raw)
        return processed
    else:
        return "!!did not extract template!!"
    

## TODO: exception on broken connections?
def cs_exchange(usr_first, usr_last, patient_num, msg):
    message = usr_first+"_"+usr_last+":patient"+str(patient_num)+"\0\0"+msg+"\0"
    cs_sock = socket.socket()
    cs_sock.connect((cs_host, cs_port))
    sent = 0
    while sent < len(message):
        sent += cs_sock.send(bytearray(message[sent:], 'UTF-8'))
    chunks = []
    reply = cs_sock.recv(cs_bufsize)
    chunks.append(reply)
    while reply != b'':
        reply = cs_sock.recv(cs_bufsize)
        chunks.append(reply)
    cs_sock.close()
    return b''.join(chunks).decode("utf-8")
    


@app.route("/conversations/", methods=['POST'])
def conversations():
    if request.method == 'POST':
        ## TODO error handling:
        ##      error if not json
        ##      error if db fails
        logger.info(request.headers)
        logger.info(request.data)
        inputs = request.get_json()
        convo_num = -1
        inputs['ws_v'] = WS_VERSION
        if not 'group' in inputs:
            if conf['service_pipeline'] == 'cs_only':
                inputs['group'] = 'control'
            elif conf['service_pipeline'] == 'cs_cnn':
                inputs['group'] = 'test'
            elif conf['service_pipeline'] == 'random':
                inputs['group'] = 'control' if random.random() < 0.5 else 'test'
            else:
                abort(500)
            ins_sql = '''INSERT INTO Conversations (Client_ID, WS_Version, First_name, Last_name, Patient_choice, Input_method, Mic, Exp_group)
                     VALUES (%(client)s, %(ws_v)s, %(first)s, %(last)s, 1, %(input)s, %(mic)s, %(group)s);'''
        num_sql = '''SELECT LAST_INSERT_ID();'''
        cursor = db.connection.cursor()
        error = False
        try:
            
            cursor.execute(ins_sql, inputs)
            db.connection.commit()
            cursor.execute(num_sql)
            convo_num = cursor.fetchone()[0]
        except:
            error = True
            db.connection.rollback()
        cursor.close()
        cs_greeting = cs_exchange(inputs['first'], inputs['last'], 1, "")
        response_dict = {}
        status = 201
        headers = {}
        if not error:
            headers['location'] = "/conversations/" + str(convo_num) + "/"
            response_dict['status'] = 'ok'
            response_dict['resource'] = url_for('show_conversation', num=convo_num)
            response_dict['conversation_num'] = convo_num
            response_dict['greeting'] = cs_greeting
        else:
            status = 500
            response_dict['status'] = 'error'
            response_dict['resource'] = ''
            response_dict['conversation_num'] = ''
            response_dict['greeting'] = ''

        response_str = json.dumps(response_dict, indent=2) + "\n"
        response = Response(response = response_str,
                            status = status,
                            headers = headers,
                            mimetype = 'application/json')
        return response

@app.route("/conversations/<int:num>/")
def show_conversation(num):
    response_dict = {}
    get_sql = '''SELECT * FROM Conversations
                 WHERE Convo_num = %s'''
    cursor = db.connection.cursor()
    try:
        cursor.execute(get_sql, str(num))
        record = cursor.fetchone()
        response_dict['num'] = record[0]
        response_dict['client'] = record[1]        
        response_dict['first'] = record[2]
        response_dict['last'] = record[3]
        response_dict['patient'] = record[4]
        response_dict['input'] = record[5]
        response_dict['mic'] = record[6]
        response_dict['group'] = record[7]
    except:
        ## TODO: make this better
        return 404
    cursor.close()
    response_str = json.dumps(response_dict, indent=2)
    response = Response(response = response_str,
                        status = 200,
                        mimetype = 'application/json')
    return response

@app.route("/conversations/<int:convo_num>/query/", methods=['POST'])
def new_query(convo_num):
    if request.method == 'POST':
        ## TODO error handling:
        ##      error if not json
        ##      error if db fails
        ##      error if conversation does not exist

        error = False
        usr_first = ""
        usr_last = ""
        last_qnum = 0
        group = ""
        usr_sql = '''SELECT First_name, Last_name, MAX(Query_num), Exp_group
                     FROM Conversations JOIN Queries
                     ON Conversations.Convo_num = Queries.Convo_num
                     WHERE Conversations.Convo_num = %s;'''
        cursor = db.connection.cursor()
        try:
            cursor.execute(usr_sql, [str(convo_num)])
            record = cursor.fetchone()
            usr_first = record[0]
            usr_last = record[1]
            group = record[3]
            if record[2] is not None:
                last_qnum = int(record[2])
            else:
                last_qnum = 0
        except BaseException as e:
            ## TODO: needs work
            error = True
            logger.error(str(e))
            return ("Error connecting to database", 500)
        # IMPORTANT NOTE!!! this (new_qnum) is how uniqueness of query keys is maintained in the DB.
        # I'm sure this is a bad idea somehow, but that's how it's happening now.
        new_qnum = last_qnum + 1 
        inputs = request.get_json()
        logger.info(inputs)
        ## ask ChatScript
        to_cs = "[ q: " + str(new_qnum) + " ] " + inputs['query']
        cs_init_reply = cs_exchange(usr_first, usr_last, 1, to_cs)
#        if "score me" in inputs['query'] and cs_init_reply is not None:
#            response_dict = {}
#            response_dict['status'] = 'ok'
#            response_str = json.dumps(response_dict, indent=2) + "\n"
#            response = Response(response = response_str,
#                                status = 201,
#                                mimetype = 'application/json')
#            return (response)
        logger.info(cs_init_reply)
        why = cs_exchange(usr_first, usr_last, 1, ":why")
        #print(why)
        cs_interp = process_match(why)
        logger.info(cs_interp)
        if group == 'test' and len(inputs['query'].split()) > 2 :
            if cs_interp != '_*':
                # NOTE! This is a hack to get around CS limitations; the logistic
                # regression model mostly only uses this feature to know whether or
                # not CS hit. This should be the log probability of the CS interpretation
                # under the CNN model.
                cs_logprob = log10(0.9) 
            else:
                cs_logprob = None
            #print(cs_interp)
            ## ask CNN
            probs, confs = cnn_predict(inputs['query'])
            #print(probs.data)
            best = best_idx(probs)
            cnn_interp = query(best)
            # cnn_reply = "NULL"
            unlog = torch.exp(probs)
            feats = compile_feats(probs.data[0][best],
                                  entropy(unlog.data[0].numpy()),
                                  confs.data[0][best],
                                  cs_logprob,
                                  cnn_interp.replace(' ', '_'))
            #print(feats)
            use_cnn = decider.switch_to_CNN(feats)
            #print(use_cnn)
            cs_re_reply = "NULL"
            if use_cnn:
                new_query = "[ q: " + str(new_qnum) + " ] " + cnn_interp
                cs_re_reply = cs_exchange(usr_first, usr_last, 1, new_query)
                reply = cs_re_reply
            else:
                reply = cs_init_reply
        else:
            reply = cs_init_reply
            use_cnn = False
            cnn_interp = None
            cs_re_reply = None
        ## set SQL input values
        ins_data = {}
        ins_data['convo_num'] = convo_num
        ins_data['query_num'] = new_qnum
        ins_data['query'] = inputs['query']
        ins_data['cs_interp'] = cs_interp
        ins_data['cnn_interp'] = cnn_interp
        ins_data['cs_init_reply'] = cs_init_reply
        ins_data['cs_retry_reply'] = cs_re_reply
        ins_data['choice'] = 'cnn' if use_cnn else 'cs'
        ins_sql = '''INSERT INTO Queries 
                     (Convo_num, Query_num, Input_text, CS_interp, CNN_interp, CS_init_reply, CS_retry_reply, Choice)
                     VALUES (%(convo_num)s, %(query_num)s, %(query)s, %(cs_interp)s, %(cnn_interp)s, %(cs_init_reply)s, %(cs_retry_reply)s, %(choice)s);'''
        try:
            cursor.execute(ins_sql, ins_data)
            db.connection.commit()
        except:
            error = True
            db.connection.rollback()
        cursor.close()
        response_dict = {}
        status = 201
        headers = {}
        if not error:
            headers['location'] = "/conversations/" + str(convo_num) + "/query/" + str(new_qnum) + "/"
            response_dict['status'] = 'ok'
            response_dict['resource'] = url_for('show_conversation', num=convo_num) + "query/" + str(new_qnum) + "/" ##FIXME (implement GET)
            #response_dict['conversation_num'] = convo_num
            response_dict['reply'] = reply
        else:
            status = 500
            response_dict['status'] = 'error'
            response_dict['resource'] = ''
            #response_dict['conversation_num'] = ''
            response_dict['reply'] = ''

        response_str = json.dumps(response_dict, indent=2) + "\n"
        response = Response(response = response_str,
                            status = status,
                            headers = headers,
                            mimetype = 'application/json')

        return response #redirect(url_for('show_conversation', num=convo_num))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ['zip', 'gz', 'wav']
    
@app.route("/conversations/<int:convo_num>/query/<int:query_num>/audio", methods=['POST'])
def add_audio(convo_num, query_num):
    if request.method == 'POST':
        status = 400
        response_dict = {}
        response_dict['status'] = 'error'
        response_dict['resource'] = ''
        response_dict['info'] = 'No file given'
        headers = {}
        # check if the post request has the file part
        if 'file' not in request.files:
            response_str = json.dumps(response_dict, indent=2) + "\n"
            return Response(response = response_str,
                            status = status,
                            headers = headers,
                            mimetype = 'application/json')
        audio = request.files['file']
        # could get an empty filename if submitted without a selection
        if audio.filename == '':
            response_str = json.dumps(response_dict, indent=2) + "\n"
            return Response(response = response_str,
                            status = status,
                            headers = headers,
                            mimetype = 'application/json')
        # check if query resource exists and no audio already
        ret_qnum = ""
        ret_audpath = ""
        select_sql = '''SELECT Query_num, Audio_path
                        FROM Queries
                        WHERE Convo_num = %s
                        AND Query_num = %s;'''
        cursor = db.connection.cursor()
        try:
            cursor.execute(select_sql, [str(convo_num), str(query_num)])
            record = cursor.fetchone()
            if record:
                ret_qnum = record[0]
                ret_audpath = record[1]
            else:
                # if we get here, there is no query with that conv/query num.
                # TODO: could create the resource and wait for the query instead of failing
                status = 409 # Conflict
                response_dict['info'] = 'No corresponding query'
                response_str = json.dumps(response_dict, indent=2) + "\n"
                return Response(response = response_str,
                                status = status,
                                headers = headers,
                                mimetype = 'application/json')
        except:
            return ("Error connecting to database", 500)
        # print(ret_qnum, ret_audpath)
        ok_to_add_audio = (ret_qnum != "" and ret_audpath is None)
        if (not ok_to_add_audio):
            response_dict['info'] = 'Audio already exists'
        if audio and allowed_file(audio.filename) and ok_to_add_audio:
            filename = secure_filename(audio.filename)
            new_audio_path = os.path.join(conf['service_audio_storage'], filename)
            audio.save(new_audio_path)
            ins_sql = ''' UPDATE Queries SET Audio_path = %s
                          WHERE Convo_num = %s AND Query_num = %s
                      '''
            try:
                cursor.execute(ins_sql, [new_audio_path, str(convo_num), str(query_num)])
                db.connection.commit()
            except:
                db.connection.rollback()
                
            status = 201
            response_dict['status'] = 'ok'
            response_dict['resource'] = url_for('show_conversation', num=convo_num) + "query/" + str(query_num) + "/audio" ##FIXME (implement GET)
            response_dict['info'] = ''
        
        cursor.close()
        response_str = json.dumps(response_dict, indent=2) + "\n"
        return Response(response = response_str,
                        status = status,
                        headers = headers,
                        mimetype = 'application/json')
    
    
if __name__ == "__main__":
    if conf['service_key'] is not None:
        http = WSGIServer((conf['service_host'], conf['service_port']),
                          app.wsgi_app,
                          keyfile=conf['service_key'],
                          certfile=conf['service_cert'],
                          log = logger,
                          error_log = logger)
    else:
        http = WSGIServer((conf['service_host'], conf['service_port']),
                          app.wsgi_app,
                          log = logger,
                          error_log = logger)        
    try:
        http.serve_forever()
    except KeyboardInterrupt:
        http.stop()
        exit(signal.SIGTERM)

    
