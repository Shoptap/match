from elasticsearch import Elasticsearch
from flask import Flask, request
from elasticsearch_driver import SignatureES
from goldberg import ImageSignature
import json
import os

# =============================================================================
# Globals

app = Flask(__name__)
es = Elasticsearch([os.environ['ELASTICSEARCH_URL']])
es_index = os.environ.get('ELASTICSEARCH_INDEX', 'images')
es_doc_type = os.environ.get('ELASTICSEARCH_DOC_TYPE', 'images')
ses = SignatureES(es, index=es_index, doc_type=es_doc_type)
gis = ImageSignature()

# =============================================================================
# Helpers

def ids_with_path(path):
    matches = es.search(index=es_index,
                        _source='_id',
                        q='path:' + json.dumps(path))
    return [m['_id'] for m in matches['hits']['hits']]

def paths_at_location(offset, limit):
    search = es.search(index=es_index,
                       from_=offset,
                       size=limit,
                       _source='path')
    return [h['_source']['path'] for h in search['hits']['hits']]

def count_images():
    return es.count(index=es_index)['count']

def delete_ids(ids):
    for i in ids:
        es.delete(index=es_index, doc_type=es_doc_type, id=i, ignore=404)

def dist_to_percent(dist):
    return (1 - dist) * 100

def get_image(url_field, file_field):
    if url_field in request.form:
        return request.form[url_field], False
    else:
        return request.files[file_field].read(), True

# =============================================================================
# Routes

@app.route('/add', methods=['POST'])
def add_handler():
    path = request.form['filepath']
    img, bs = get_image('url', 'image')

    old_ids = ids_with_path(path)
    ses.add_image(path, img, bytestream=bs)
    delete_ids(old_ids)

    return json.dumps({
        'status': 'ok',
        'error': [],
        'method': 'add',
        'result': []
    })

@app.route('/delete', methods=['DELETE'])
def delete_handler():
    path = request.form['filepath']
    ids = ids_with_path(path)
    delete_ids(ids)
    return json.dumps({
        'status': 'ok',
        'error': [],
        'method': 'delete',
        'result': []
    })

@app.route('/search', methods=['POST'])
def search_handler():
    img, bs = get_image('url', 'image')
    all_orient = request.form.get('all_orientations', 'true') == 'true'

    matches = ses.search_image(
            path=img,
            all_orientations=all_orient,
            bytestream=bs)

    return json.dumps({
        'status': 'ok',
        'error': [],
        'method': 'search',
        'result': [{
            'score': dist_to_percent(m['dist']),
            'filepath': m['path']
        } for m in matches]
    })

@app.route('/compare', methods=['POST'])
def compare_handler():
    img1, bs1 = get_image('url1', 'image1')
    img2, bs2 = get_image('url2', 'image2')
    img1_sig = gis.generate_signature(img1, bytestream=bs1)
    img2_sig = gis.generate_signature(img2, bytestream=bs2)
    score = dist_to_percent(gis.normalized_distance(img1_sig, img2_sig))

    return json.dumps({
        'status': 'ok',
        'error': [],
        'method': 'compare',
        'result': [{ 'score': score }]
    })

@app.route('/count', methods=['GET'])
def count_handler():
    count = count_images()
    return json.dumps({
        'status': 'ok',
        'error': [],
        'method': 'count',
        'result': [count]
    })

@app.route('/list', methods=['GET'])
def list_handler():
    offset = max(int(request.form.get('offset', 0)), 0)
    limit = max(int(request.form.get('limit', 20)), 0)
    paths = paths_at_location(offset, limit)

    return json.dumps({
        'status': 'ok',
        'error': [],
        'method': 'list',
        'result': paths
    })

@app.route('/ping', methods=['GET'])
def ping_handler():
    return json.dumps({
        'status': 'ok',
        'error': [],
        'method': 'ping',
        'result': []
    })

# =============================================================================
# Error Handling

@app.errorhandler(400)
def page_not_found(e):
    return json.dumps({
        'status': 'fail',
        'error': ['bad request'],
        'method': '',
        'result': []
    }), 400

@app.errorhandler(404)
def page_not_found(e):
    return json.dumps({
        'status': 'fail',
        'error': ['not found'],
        'method': '',
        'result': []
    }), 404

@app.errorhandler(405)
def page_not_found(e):
    return json.dumps({
        'status': 'fail',
        'error': ['method not allowed'],
        'method': '',
        'result': []
    }), 405

@app.errorhandler(500)
def page_not_found(e):
    return json.dumps({
        'status': 'fail',
        'error': [str(e)],
        'method': '',
        'result': []
    }), 500
