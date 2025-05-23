# Nitram-DB-Finance-bot-LLM

## Overview

Nitram FinanceBot is an internal web-based assistant designed specifically for bank employees. It allows staff to interact with customer financial data through natural language queries. Built with Flask, PostgreSQL, web application and integrated with Groq’s LLM API, the bot interprets user input, generates SQL queries dynamically, and responds in a professional, conversational tone.

## Features

>> - Query customer details, account balances, and loan information using plain English.
>> - Retrieve aggregated insights such as total bank loans or deposits.
>> - Maintain conversational context for more intuitive interaction.
>> - Uses Groq’s LLaMA-based model for SQL generation and natural language responses.

## Architecture

>> - **Backend**: Python, Flask, psycopg2, Groq API.
>> - **Database**: PostgreSQL with a structured financial schema.
>> - **LLM Integration**: Groq LLaMA3-8B via Groq’s API for query generation and natural responses.

## How it works

1. User types a natural language question.
2. Groq API interprets the question and generates a PostgreSQL query.
3. Bot executes the SQL against a live database.
4. Groq generates a human-like, professional response based on the query result.

## Deployment

The Financial bot was Deployed via render as a web application (Flask frontend). To access the the finance bot click the link below
>>> [Deployment Link]
