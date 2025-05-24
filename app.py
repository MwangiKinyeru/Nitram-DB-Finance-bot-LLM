from flask import Flask, request, jsonify, render_template, abort
from flask_cors import CORS
from groq_test import FinanceBot
import logging
import os

# Initialize Flask app with template folder
app = Flask(__name__, template_folder='templates')

CORS(app, origins=[
    "http://localhost:*",
    "http://127.0.0.1:*",
    "https://nitram-db-finance-bot-llm-1.onrender.com"
], supports_credentials=True)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FinanceBot
try:
    bot = FinanceBot()
    logger.info("FinanceBot initialized successfully")
    
    # Use the new test_connection() method here
    if not bot.test_connection():
        raise RuntimeError("Database test query failed")
    logger.info("✅ FinanceBot connection verified")

except Exception as e:
    logger.error(f"Failed to initialize FinanceBot: {str(e)}")
    raise

# Serve HTML from templates folder
@app.route('/')
def serve_index():
    try:
        return render_template('index.html')
    except Exception as e:
        logger.error(f"Error loading index.html: {str(e)}")
        abort(404, description="index.html not found in templates folder.")

# API endpoint for chat queries
@app.route('/ask', methods=['POST'])
def ask():
    try:
        logger.info(f"Incoming request headers: {request.headers}")
        logger.info(f"Request data: {request.data}")
        
        if not request.is_json:
            logger.warning("Request missing JSON content type")
            return jsonify({'error': 'Content-Type must be application/json'}), 415
            
        data = request.get_json()
        
        if not data or 'query' not in data:
            logger.warning("Missing query parameter")
            return jsonify({'error': 'Missing query parameter'}), 400
            
        user_query = data['query'].strip()
        if not user_query:
            logger.warning("Empty query received")
            return jsonify({'error': 'Query cannot be empty'}), 400
        
        logger.info(f"Processing query: {user_query}")
        
        # Process query through FinanceBot
        bot_response = bot.ask(user_query)
        logger.info(f"Generated response: {bot_response[:200]}...")
        
        return jsonify({
            'response': bot_response,
            'status': 'success'
        })
    
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}", exc_info=True)
        return jsonify({
            'error': 'An error occurred while processing your request',
            'status': 'error'
        }), 500

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)
