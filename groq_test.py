import os
import re
import json
import logging
import requests
import psycopg2
from psycopg2 import pool
from urllib.parse import urlparse
from dotenv import load_dotenv
from datetime import datetime, date
from decimal import Decimal

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FinanceBot:
    def __init__(self):
        # Parse DATABASE_URL
        db_url = os.getenv("DATABASE_URL")
        parsed = urlparse(db_url)

        self.db_pool = psycopg2.pool.SimpleConnectionPool(
            minconn=1,
            maxconn=10,
            user=parsed.username,
            password=parsed.password,
            host=parsed.hostname,
            port=parsed.port,
            database=parsed.path[1:]  # skip leading slash
        )

        self.schema = self._load_schema()
        self.context = {
            'current_account': None,
            'current_customer': None,
            'last_query_type': None,
            'conversation_history': []
        }

    def test_connection(self):
        conn = self.db_pool.getconn()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                return cursor.fetchone()[0] == 1
        except Exception as e:
            logger.error(f"Database connection test failed: {str(e)}")
            return False
        finally:
            self.db_pool.putconn(conn)

    def _load_schema(self):
        conn = self.db_pool.getconn()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT table_name, column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_schema = 'public'
                    ORDER BY table_name, ordinal_position;
                """)
                schema = {}
                for table, column, dtype in cursor.fetchall():
                    schema.setdefault(table, []).append((column, dtype))
                return schema
        except Exception as e:
            logger.error(f"Error loading schema: {str(e)}")
            return {}
        finally:
            self.db_pool.putconn(conn)

    def _generate_sql(self, user_query):
        if not self.schema:
            return None
        try:
            schema_info = "\n".join(
                f"Table {table}: {', '.join(f'{col} ({dtype})' for col, dtype in columns)}"
                for table, columns in self.schema.items()
            )
            history = "\n".join([f"User: {q}\nBot: {a}" for q, a in self.context['conversation_history'][-3:]])

            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": os.getenv("GROQ_MODEL", "llama3-8b-8192"),
                    "messages": [
                        {"role": "system", "content": f"""
                            You are a financial SQL expert. Convert user questions into PostgreSQL queries.
                            Database Schema:
                            {schema_info}
                            Conversation History:
                            {history}
                            Context:
                            {json.dumps(self.context)}
                            Rules:
                            1. Use lowercase table/column names.
                            2. Join tables where necessary.
                            3. For totals, use SUM().
                            4. Return SQL inside ```sql``` blocks only.
                        """},
                        {"role": "user", "content": user_query}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 500
                },
                timeout=30
            )

            response.raise_for_status()
            content = response.json()['choices'][0]['message']['content']
            match = re.search(r"```sql\s*(.*?)```", content, re.DOTALL | re.IGNORECASE)
            return match.group(1).strip() if match else None
        except Exception as e:
            logger.error(f"SQL generation error: {str(e)}")
            return None

    def _execute_query(self, sql):
        conn = self.db_pool.getconn()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                rows = cursor.fetchall()
                headers = [desc[0] for desc in cursor.description]
                return [dict(zip(headers, row)) for row in rows]
        except Exception as e:
            logger.error(f"Query execution error: {str(e)}")
            return None
        finally:
            self.db_pool.putconn(conn)

    def _generate_natural_response(self, data, user_query):
        if not data:
            return "Sorry, I couldn’t find any matching records."

        try:
            def format_value(v):
                if isinstance(v, (Decimal, float, int)):
                    return float(v)
                if isinstance(v, (datetime, date)):
                    return v.strftime("%Y-%m-%d")
                return str(v)

            formatted_data = [
                {k: format_value(v) for k, v in row.items()} for row in data
            ]

            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": os.getenv("GROQ_MODEL", "llama3-8b-8192"),
                    "messages": [
                        {"role": "system", "content": """
                            You are a professional financial assistant for a bank. Given a user query and matching database records,
                            generate a clear, accurate, and concise response. Your tone should reflect how a bank staff member communicates
                            in a professional setting—whether summarizing data for internal review or preparing information to relay 
                            to a customer. Focus on key figures, avoid unnecessary filler, and vary your phrasing naturally based on 
                            the query type.
                        """},
                        {"role": "user", "content": f"""
                            User asked: \"{user_query}\"

                            Here is the data from the database that matches the query:
                            {json.dumps(formatted_data, indent=2)}
                        """}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 300
                },
                timeout=30
            )

            response.raise_for_status()
            reply = response.json()['choices'][0]['message']['content'].strip()
            return reply
        except Exception as e:
            logger.error(f"Natural response generation error: {str(e)}")
            return f"{len(data)} records found, but I couldn't format a response."

    def _update_context(self, user_query, response_text):
        self.context['conversation_history'].append((user_query, response_text))
        if len(self.context['conversation_history']) > 5:
            self.context['conversation_history'] = self.context['conversation_history'][-5:]

    def ask(self, user_query):
        sql = self._generate_sql(user_query)
        if not sql:
            return "Sorry, I couldn't generate a valid SQL query for that."
        results = self._execute_query(sql)
        if results is None:
            return "Sorry, I couldn't retrieve any data for that."
        response = self._generate_natural_response(results, user_query)
        self._update_context(user_query, response)
        return response

# CLI Entry point
if __name__ == "__main__":
    try:
        bot = FinanceBot()
        print("Nitram BankBot\nHello! I'm your Nitram Bank assistant. How can I help you today?")
        while True:
            try:
                user_input = input("You: ").strip()
                if user_input.lower() in ['exit', 'quit']:
                    print("Nitram: Alright, talk to you later.")
                    break
                reply = bot.ask(user_input)
                print(f"Nitram: {reply}")
            except KeyboardInterrupt:
                print("\nNitram: Session ended. Take care!")
                break
    except Exception as e:
        logger.error(f"Bot failed to start: {str(e)}")
