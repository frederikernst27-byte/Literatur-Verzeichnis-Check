#!/usr/bin/env python3
"""Pollt ein IMAP-Postfach auf neue Mails mit PDF-Anhang, prüft das
Literaturverzeichnis und schickt das Excel-Ergebnis als Antwortmail zurück.

Muss von PIA-Lab selbst dauerhaft laufen gelassen werden (z.B. per Cron oder
als systemd-Service) - siehe README.md.
"""
from __future__ import annotations

import email
import imaplib
import os
import smtplib
import tempfile
import time
import traceback
from email.message import EmailMessage

from dotenv import load_dotenv

from src.pipeline import run_pipeline_to_excel
from src.verify.ai_search import AIProviderError


def fetch_unseen_pdfs(imap_host: str, imap_port: int, user: str, password: str):
    """Liefert (uid, from_addr, subject, pdf_bytes) für jede ungelesene Mail mit PDF-Anhang."""
    with imaplib.IMAP4_SSL(imap_host, imap_port) as conn:
        conn.login(user, password)
        conn.select("INBOX")
        status, data = conn.search(None, "UNSEEN")
        if status != "OK":
            return
        for uid in data[0].split():
            status, msg_data = conn.fetch(uid, "(RFC822)")
            if status != "OK":
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            from_addr = email.utils.parseaddr(msg.get("From"))[1]
            subject = msg.get("Subject", "Literaturverzeichnis-Pruefung")

            for part in msg.walk():
                if part.get_content_type() == "application/pdf":
                    yield uid.decode(), from_addr, subject, part.get_payload(decode=True)
                    break


def send_reply(smtp_host: str, smtp_port: int, user: str, password: str,
                to_addr: str, subject: str, body: str, attachment_path: str):
    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = to_addr
    msg["Subject"] = f"Re: {subject}"
    msg.set_content(body)

    with open(attachment_path, "rb") as f:
        msg.add_attachment(
            f.read(),
            maintype="application",
            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename="literaturpruefung.xlsx",
        )

    with smtplib.SMTP(smtp_host, smtp_port) as conn:
        conn.starttls()
        conn.login(user, password)
        conn.send_message(msg)


def process_inbox():
    imap_host, imap_port = os.environ["IMAP_HOST"], int(os.environ.get("IMAP_PORT", 993))
    imap_user, imap_password = os.environ["IMAP_USER"], os.environ["IMAP_PASSWORD"]
    smtp_host, smtp_port = os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", 587))
    smtp_user, smtp_password = os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"]

    for uid, from_addr, subject, pdf_bytes in fetch_unseen_pdfs(imap_host, imap_port, imap_user, imap_password):
        print(f"Neue Mail von {from_addr} (uid {uid}), verarbeite PDF...")
        with tempfile.TemporaryDirectory() as tmp_dir:
            pdf_path = os.path.join(tmp_dir, "input.pdf")
            xlsx_path = os.path.join(tmp_dir, "literaturpruefung.xlsx")
            with open(pdf_path, "wb") as f:
                f.write(pdf_bytes)

            try:
                run_pipeline_to_excel(pdf_path, xlsx_path)
                body = "Anbei die Pruefung des Literaturverzeichnisses."
            except AIProviderError as e:
                body = f"Fehler bei der KI-Pruefung: {e}\nEs wurde nur die API-basierte Pruefung durchgefuehrt, sofern moeglich."
            except Exception:
                body = f"Bei der Verarbeitung ist ein Fehler aufgetreten:\n\n{traceback.format_exc()}"
                xlsx_path = None

            if xlsx_path and os.path.exists(xlsx_path):
                send_reply(smtp_host, smtp_port, smtp_user, smtp_password, from_addr, subject, body, xlsx_path)
            else:
                send_reply_text_only(smtp_host, smtp_port, smtp_user, smtp_password, from_addr, subject, body)


def send_reply_text_only(smtp_host, smtp_port, user, password, to_addr, subject, body):
    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = to_addr
    msg["Subject"] = f"Re: {subject}"
    msg.set_content(body)
    with smtplib.SMTP(smtp_host, smtp_port) as conn:
        conn.starttls()
        conn.login(user, password)
        conn.send_message(msg)


def main():
    load_dotenv()
    interval = int(os.environ.get("POLL_INTERVAL_SECONDS", 60))
    print(f"Starte E-Mail-Bot, Poll-Intervall {interval}s ...")
    while True:
        try:
            process_inbox()
        except Exception:
            print("Fehler beim Verarbeiten des Postfachs:")
            traceback.print_exc()
        time.sleep(interval)


if __name__ == "__main__":
    main()
