import os, sys, json, secrets, string, datetime, shutil, subprocess
from flask import Flask, render_template, session, redirect, request, url_for, abort, Response
from flask_sqlalchemy import SQLAlchemy
from flask_sqlalchemy.query import Query
from models import db, Post
from typing import Union, Optional, Any
from dotenv import load_dotenv

load_dotenv()
app : Flask = Flask(__name__)
app.secret_key = secrets.token_hex(16)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///data.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

file_dir : str = os.path.dirname(os.path.realpath(__file__))
frozen_dir : str = os.path.dirname(sys.executable)
executable_dir : str = file_dir
if getattr(sys, 'frozen', False):
    executable_dir = frozen_dir


def generate_id(length:int=12) -> str:
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(length))


def generate_unique_id(length:int=12) -> str:
    candidate : str = generate_id(length)
    while Post.query.filter_by(short_id=candidate).first():
        candidate : str = generate_id(length)
    return candidate


with app.app_context():
    db.create_all()

CERT_FILE : str = os.path.join(executable_dir, 'instance', 'cert.pem')
KEY_FILE : str = os.path.join(executable_dir, 'instance', 'key.pem')


def generate_self_signed_cert(cert_file: str = CERT_FILE, key_file: str = KEY_FILE) -> None:
    '''Generate a self-signed certificate if it does not exist.'''
    if os.path.isfile(cert_file) and os.path.isfile(key_file):
        return

    if not shutil.which('openssl'):
        print('(openssl) not found. No certificates generated.')

    print('Generating self-signed certificate...')
    subprocess.run(
        [
            'openssl',
            'req',
            '-x509',
            '-newkey',
            'rsa:4096',
            '-keyout',
            key_file,
            '-out',
            cert_file,
            '-days',
            '365',
            '-nodes',
            '-subj',
            '/CN=localhost',
        ],
        check=True,
    )
    print('Self-signed certificate generated.')


@app.route('/')
def index() -> Union[str, Any]:
    short_id : str = request.args.get('p', '')
    if short_id:
        return redirect(url_for('post', short_id=short_id))
    return render_template('index.html')

@app.route('/submit', methods=['GET', 'POST'])
def submit_post() -> Union[str, Any]:

    if request.method == 'POST':
        title : Optional[str] = request.form['title']
        content_delta : Optional[str] = request.form['post_contents']
        if not title:
            return render_template('submit_post.html')
        short_id : str = generate_unique_id()
        new_post : Post = Post(short_id=short_id, title=title, content_delta=content_delta)
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for('post', short_id=short_id))

    return render_template('submit_post.html')


@app.route('/modify/<short_id>', methods=['GET', 'POST'])
def modify_post(short_id:str) -> Union[str, Any]:
    post : Post = Post.query.filter_by(short_id=short_id).first_or_404()

    if request.method == 'POST':
        title : Optional[str] = request.form['title']
        content_delta : Optional[str] = request.form['post_contents']
        if not title:
            return render_template('submit_post.html')
        post.title = title
        post.content_delta = content_delta
        post.modified_at = datetime.datetime.utcnow()
        db.session.commit()
        return redirect(url_for('post', short_id=short_id))

    return render_template('modify_post.html', post_data=post)

@app.route('/post/<short_id>', methods=['GET', 'POST'])
def post(short_id:str) -> Union[str, Any]:
    post : Post = Post.query.filter_by(short_id=short_id).first_or_404()
    return render_template('post.html', post_data=post)

@app.route('/browse', methods=['GET', 'POST'])
def browse() -> Union[str, Any]:
    posts : list[Post] = Post.query.order_by(Post.created_at.desc()).all()
    if request.method == 'POST':
        search_query : str = request.form.get('search_query', '').strip().lower()
        if search_query:
            query : Query = Post.query.filter(Post.title.ilike(f'%{search_query}%'))
            results : list[Post] = query.all()
            return render_template('browse.html', posts=results, board=f'SEARCH ({request.form.get('search_type', 'title').upper()}) [{search_query}]')
    return render_template('browse.html', posts=posts, board='ALL')

@app.route('/delete/<short_id>')
def delete_post(short_id:str) -> Union[str, Any]:
    post : Post = Post.query.filter_by(short_id=short_id).first_or_404()
    db.session.delete(post)
    db.session.commit()
    return redirect(url_for('browse'))

@app.errorhandler(401)
def not_allowed(_error) -> Union[str, Any]:
    return render_template('401.html')

@app.errorhandler(404)
def not_found(_error) -> Union[str, Any]:
    return render_template('404.html')

if __name__ == '__main__':
    generate_self_signed_cert()
    port : int = 5000
    print(f'Inklet Server running on port {port}')
    app.run(host='0.0.0.0', port=port, ssl_context=(CERT_FILE, KEY_FILE))
