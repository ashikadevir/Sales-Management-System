import mysql.connector
import streamlit as st

def get_db_connection():
    """Establishes connection to the MySQL database."""
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="root",  # ⚠️ Replace with your actual MySQL password
        database="sales_management",
        use_pure=True
    )

def run_query(query, params=None, fetch_all=True):
    """Executes SELECT queries and returns dictionary results."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(query, params or ())
        if fetch_all:
            result = cursor.fetchall()
        else:
            result = cursor.fetchone()
        return result
    finally:
        cursor.close()
        conn.close()

def execute_commit(query, params=None):
    """Executes INSERT, UPDATE, and DELETE queries with commit."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(query, params or ())
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        conn.close()