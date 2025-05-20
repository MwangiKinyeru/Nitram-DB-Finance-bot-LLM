import os
import re
import json
import logging
import requests
import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv
from datetime import datetime
from decimal import Decimal

# Load env variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)

class FinanceBot:
    def __init__(self):
        self.db_pool = psycopg2.pool.SimpleConnectionPool(
            minconn=1,
            maxconn=10,
            host=os.getenv("DB_HOST"),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            port=os.getenv("DB_PORT")
        )

        self.schema = self._load_schema()
        self.context = {
            'current_account': None,
            'current_customer': None,
            'last_query_type': None,
            'conversation_history': []
        }

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
            logging.error(f"Error loading schema: {str(e)}")
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
                            You are a financial database expert. Convert user questions to PostgreSQL SQL.
                            Database Schema:
                            {schema_info}
                            Conversation History:
                            {history}
                            Current Context:
                            {json.dumps(self.context, indent=2)}
                            Rules:
                            1. Use exact table/column names (all lowercase)
                            2. For customer info: JOIN account and customers
                            3. For transactions: JOIN transactions and account
                            4. For loans: JOIN loans and customers
                            5. For "last X": ORDER BY date DESC LIMIT 1
                            6. NEVER use placeholder values
                            7. ONLY return SQL in ```sql``` blocks
                            8. Include all necessary WHERE clauses
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
            sql_match = re.search(r"```sql\s*(.*?)\s*```", content, re.DOTALL | re.IGNORECASE)
            return sql_match.group(1).strip() if sql_match else None
        except Exception as e:
            logging.error(f"SQL generation error: {str(e)}")
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
            logging.error(f"Query execution error: {str(e)}")
            return None
        finally:
            self.db_pool.putconn(conn)

    def _update_context(self, user_query, response_text):
        self.context['conversation_history'].append((user_query, response_text))
        if len(self.context['conversation_history']) > 5:
            self.context['conversation_history'] = self.context['conversation_history'][-5:]

    def _format_response(self, results):
        if not results:
            return "No data found or an error occurred."
        return json.dumps(results, indent=2, default=str)

    def ask(self, user_query):
        sql = self._generate_sql(user_query)
        if not sql:
            return "Sorry, I couldn't generate a valid SQL query for that."
        results = self._execute_query(sql)
        response = self._format_response(results)
        self._update_context(user_query, response)
        return response

# CLI Entry point
if __name__ == "__main__":
    try:
        bot = FinanceBot()
        print("Finance Bot: Hello! How can I help you with your banking questions today?")

        while True:
            try:
                user_input = input("You: ").strip()
                if user_input.lower() in ['exit', 'quit']:
                    print("Finance Bot: Goodbye! Have a great day.")
                    break
                response = bot.ask(user_input)
                print(f"Finance Bot:\n{response}")
            except KeyboardInterrupt:
                print("\nFinance Bot: Goodbye!")
                break
    except Exception as e:
        logging.error(f"Failed to start Finance Bot: {str(e)}")
