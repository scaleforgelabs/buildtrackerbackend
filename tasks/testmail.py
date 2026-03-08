import smtplib
from email.message import EmailMessage

msg = EmailMessage()
msg["Subject"] = "Test Email from Python"
msg["From"] = "allishittuabdulhameed@gmail.com"
msg["To"] = "ojugbelelateef2006@gmail.com"
msg.set_content("Hello 👋 This is a test email sent using Python SMTP.")

smtp_server = "smtp.gmail.com"
port = 465  # SSL port

with smtplib.SMTP_SSL(smtp_server, port) as server:
    server.login("allishittuabdulhameed@gmail.com", "annhzrqydscdbydu")
    server.send_message(msg)

print("Email sent successfully!")