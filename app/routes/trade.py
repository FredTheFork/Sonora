from flask import Blueprint, render_template

trade_bp = Blueprint('trade', __name__, url_prefix='/trade')

@trade_bp.route('/')
def trade():
    return render_template("trade.html")