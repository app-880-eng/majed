services:
  - type: worker
    name: pumpfun-sniper
    runtime: python
    buildCommand: pip install -r requirements.txt
    startCommand: python main.py