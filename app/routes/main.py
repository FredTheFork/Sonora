from flask import Blueprint, render_template, redirect, url_for
from flask_login import current_user

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def login():
    # If already logged in, go to home
    if current_user.is_authenticated:
        return redirect(url_for('pool.daily_pool'))
    
    return render_template('login.html')