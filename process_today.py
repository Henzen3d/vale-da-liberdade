#!/usr/bin/env python3
"""Processa o episódio de hoje usando o pipeline."""
import sys
import os

sys.path.insert(0, '/home/osmar/web-jornal-vale-da-liberdade/scripts')
os.chdir('/home/osmar/web-jornal-vale-da-liberdade')

from dotenv import load_dotenv
load_dotenv('.env')

from pipeline import main as pipeline_main

from datetime import date
today = date.today().isoformat()
sys.argv = ['pipeline.py', 'process', '--date', today]
pipeline_main()
