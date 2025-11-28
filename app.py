from flask import Flask, render_template, render_template_string, request, jsonify, redirect, url_for, send_file
import requests
import base64
import os
import dotenv
from decimal import Decimal
from datetime import datetime
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "secret-key")

PAYPAL_CLIENT_ID = os.environ.get("PAYPAL_CLIENT_ID") 
PAYPAL_CLIENT_SECRET = os.environ.get("PAYPAL_CLIENT_SECRET")
PAYPAL_API_BASE = os.environ.get("PAYPAL_API_BASE", "https://api-m.paypal.com")

receipt_data_store = {}

def get_access_token():
    url = f"{PAYPAL_API_BASE}/v1/oauth2/token"
    print(f"Client ID: {PAYPAL_CLIENT_ID}")
    print(f"Using API Base: {PAYPAL_API_BASE}")
    
    credentials = f"{PAYPAL_CLIENT_ID}:{PAYPAL_CLIENT_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    
    headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    data = {"grant_type": "client_credentials"}
    response = requests.post(url, headers=headers, data=data)
    
    if response.status_code == 200:
        return response.json()["access_token"]
    else:
        raise Exception(f"Failed to get access token: {response.text}")

def create_order(amount):
    access_token = get_access_token()
    url = f"{PAYPAL_API_BASE}/v2/checkout/orders"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }
    
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "amount": {
                    "currency_code": "USD",
                    "value": str(amount)
                },
                "description": "Payment for services"
            }
        ],
        "application_context": {
            "return_url": request.url_root + "payment/success",
            "cancel_url": request.url_root + "payment/cancel",
            "brand_name": "My Flask Store",
            "landing_page": "BILLING",
            "user_action": "PAY_NOW"
        }
    }
    
    response = requests.post(url, json=payload, headers=headers)
    
    if response.status_code == 201:
        order_data = response.json()
        approval_url = next(
            link["href"] for link in order_data["links"] 
            if link["rel"] == "approve"
        )
        return order_data["id"], approval_url
    else:
        raise Exception(f"Failed to create order: {response.text}")

def capture_order(order_id):
    access_token = get_access_token()
    url = f"{PAYPAL_API_BASE}/v2/checkout/orders/{order_id}/capture"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }
    
    response = requests.post(url, headers=headers)
    
    if response.status_code == 201:
        return response.json()
    else:
        raise Exception(f"Failed to capture order: {response.text}")

def generate_pdf_receipt(receipt_data):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
    
    elements = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#0070ba'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    elements.append(Paragraph("PAYMENT RECEIPT", title_style))
    elements.append(Spacer(1, 0.3*inch))
    
    company_info = [
        ["BFL Technologies"],
        ["00100 Nairobi, Kenya"],
        ["+254 700 000000"],
        ["bflkenya@gmail.com"]
    ]
    
    company_table = Table(company_info, colWidths=[6*inch])
    company_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.grey),
    ]))
    elements.append(company_table)
    elements.append(Spacer(1, 0.3*inch))
    
    receipt_info = [
        ['Receipt Date:', receipt_data['date']],
        ['Transaction ID:', receipt_data['transaction_id']],
        ['Order ID:', receipt_data['order_id']],
    ]
    
    info_table = Table(receipt_info, colWidths=[2*inch, 4*inch])
    info_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8f9fa')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 0.3*inch))
    
    elements.append(Paragraph("<b>Customer Information</b>", styles['Heading2']))
    elements.append(Spacer(1, 0.1*inch))
    
    customer_info = [
        ['Name:', receipt_data['payer_name']],
        ['Email:', receipt_data['payer_email']],
    ]
    
    customer_table = Table(customer_info, colWidths=[2*inch, 4*inch])
    customer_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(customer_table)
    elements.append(Spacer(1, 0.3*inch))
    
    elements.append(Paragraph("<b>Payment Details</b>", styles['Heading2']))
    elements.append(Spacer(1, 0.1*inch))
    
    payment_details = [
        ['Description', 'Amount'],
        ['Payment for services', f"${receipt_data['amount']} {receipt_data['currency']}"],
    ]
    
    payment_table = Table(payment_details, colWidths=[4*inch, 2*inch])
    payment_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0070ba')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(payment_table)
    elements.append(Spacer(1, 0.2*inch))
    
    total_data = [['TOTAL PAID:', f"${receipt_data['amount']} {receipt_data['currency']}"]]
    total_table = Table(total_data, colWidths=[4*inch, 2*inch])
    total_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'RIGHT'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 14),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#e8f4f8')),
        ('BOX', (0, 0), (-1, -1), 2, colors.HexColor('#0070ba')),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
    ]))
    elements.append(total_table)
    elements.append(Spacer(1, 0.3*inch))
    
    status_data = [['Payment Status:', receipt_data['status']]]
    status_table = Table(status_data, colWidths=[2*inch, 4*inch])
    status_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('TEXTCOLOR', (1, 0), (1, -1), colors.green),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(status_table)
    elements.append(Spacer(1, 0.5*inch))
    
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.grey,
        alignment=TA_CENTER
    )
    elements.append(Paragraph("Thank you for your payment!", footer_style))
    elements.append(Spacer(1, 0.1*inch))
    elements.append(Paragraph("This is a computer-generated receipt and requires no signature.", footer_style))
    
    doc.build(elements)
    buffer.seek(0)
    return buffer

@app.route('/')
def index():
    return render_template('payment.html')

@app.route('/create-payment', methods=['POST'])
def create_payment():
    try:
        amount = request.form.get('amount')
        amount = Decimal(amount)
        if amount <= 0:
            return "Amount must be greater than 0", 400
        
        order_id, approval_url = create_order(amount)
        return redirect(approval_url)
        
    except Exception as e:
        return f"Error creating payment: {str(e)}", 500

@app.route('/payment/success')
def payment_success():
    try:
        order_id = request.args.get('token')
        capture_data = capture_order(order_id)
        
        status = capture_data["status"]
        payer_email = capture_data["payer"]["email_address"]
        payer_name = capture_data["payer"]["name"]["given_name"] + " " + capture_data["payer"]["name"]["surname"]
        amount = capture_data["purchase_units"][0]["payments"]["captures"][0]["amount"]["value"]
        currency = capture_data["purchase_units"][0]["payments"]["captures"][0]["amount"]["currency_code"]
        transaction_id = capture_data["purchase_units"][0]["payments"]["captures"][0]["id"]
        
        receipt_data_store[transaction_id] = {
            'transaction_id': transaction_id,
            'order_id': order_id,
            'payer_name': payer_name,
            'payer_email': payer_email,
            'amount': amount,
            'currency': currency,
            'status': status,
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        html = f'''
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Payment Success</title>
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
            <style>
                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }}
                
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
                    min-height: 100vh;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    padding: 20px;
                }}
                
                .container {{
                    background: white;
                    padding: 40px;
                    border-radius: 20px;
                    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
                    max-width: 550px;
                    width: 100%;
                    animation: slideIn 0.5s ease-out;
                }}
                
                @keyframes slideIn {{
                    from {{
                        opacity: 0;
                        transform: scale(0.9);
                    }}
                    to {{
                        opacity: 1;
                        transform: scale(1);
                    }}
                }}
                
                .success-icon {{
                    text-align: center;
                    margin-bottom: 25px;
                }}
                
                .success-icon i {{
                    font-size: 80px;
                    color: #38ef7d;
                    animation: checkmark 0.8s ease-out;
                }}
                
                @keyframes checkmark {{
                    0% {{
                        transform: scale(0);
                        opacity: 0;
                    }}
                    50% {{
                        transform: scale(1.2);
                    }}
                    100% {{
                        transform: scale(1);
                        opacity: 1;
                    }}
                }}
                
                h1 {{
                    text-align: center;
                    color: #333;
                    font-size: 28px;
                    margin-bottom: 10px;
                }}
                
                .subtitle {{
                    text-align: center;
                    color: #666;
                    margin-bottom: 30px;
                    font-size: 14px;
                }}
                
                .details-card {{
                    background: #f8f9fa;
                    border-radius: 15px;
                    padding: 25px;
                    margin-bottom: 20px;
                }}
                
                .detail-row {{
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    padding: 12px 0;
                    border-bottom: 1px solid #e0e0e0;
                }}
                
                .detail-row:last-child {{
                    border-bottom: none;
                }}
                
                .detail-label {{
                    color: #666;
                    font-size: 14px;
                    display: flex;
                    align-items: center;
                    gap: 8px;
                }}
                
                .detail-label i {{
                    color: #38ef7d;
                    width: 20px;
                }}
                
                .detail-value {{
                    color: #333;
                    font-weight: 600;
                    font-size: 14px;
                    text-align: right;
                }}
                
                .amount-highlight {{
                    background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
                    color: white;
                    padding: 20px;
                    border-radius: 10px;
                    text-align: center;
                    margin: 20px 0;
                }}
                
                .amount-highlight .label {{
                    font-size: 14px;
                    opacity: 0.9;
                    margin-bottom: 5px;
                }}
                
                .amount-highlight .value {{
                    font-size: 36px;
                    font-weight: bold;
                }}
                
                .btn-home {{
                    display: block;
                    width: 100%;
                    padding: 15px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    text-align: center;
                    text-decoration: none;
                    border-radius: 10px;
                    font-weight: 600;
                    transition: all 0.3s ease;
                    margin-top: 20px;
                }}
                
                .btn-home:hover {{
                    transform: translateY(-2px);
                    box-shadow: 0 10px 25px rgba(102, 126, 234, 0.3);
                }}
                
                .transaction-id {{
                    text-align: center;
                    margin-top: 20px;
                    padding: 15px;
                    background: #fff3cd;
                    border-radius: 10px;
                    border-left: 4px solid #ffc107;
                }}
                
                .transaction-id p {{
                    color: #856404;
                    font-size: 12px;
                    margin-bottom: 5px;
                }}
                
                .transaction-id code {{
                    color: #333;
                    font-weight: 600;
                    font-size: 13px;
                    word-break: break-all;
                }}
                
                .receipt-actions {{
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                    gap: 10px;
                    margin-top: 20px;
                }}
                
                .btn-receipt {{
                    padding: 12px;
                    border: none;
                    border-radius: 10px;
                    font-weight: 600;
                    cursor: pointer;
                    transition: all 0.3s ease;
                    font-size: 14px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    gap: 8px;
                }}
                
                .btn-download {{
                    background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                    color: white;
                    text-decoration: none;
                }}
                
                .btn-download:hover {{
                    transform: translateY(-2px);
                    box-shadow: 0 5px 15px rgba(245, 87, 108, 0.3);
                }}
                
                .btn-print {{
                    background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
                    color: white;
                }}
                
                .btn-print:hover {{
                    transform: translateY(-2px);
                    box-shadow: 0 5px 15px rgba(79, 172, 254, 0.3);
                }}
                
                @media print {{
                    body {{
                        background: white;
                    }}
                    .receipt-actions, .btn-home {{
                        display: none;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="success-icon">
                    <i class="fas fa-check-circle"></i>
                </div>
                
                <h1>Payment Successful!</h1>
                <p class="subtitle">Your transaction has been completed successfully</p>
                
                <div class="amount-highlight">
                    <div class="label">Amount Paid</div>
                    <div class="value">${amount} {currency}</div>
                </div>
                
                <div class="details-card">
                    <div class="detail-row">
                        <div class="detail-label">
                            <i class="fas fa-user"></i>
                            Payer Name
                        </div>
                        <div class="detail-value">{payer_name}</div>
                    </div>
                    
                    <div class="detail-row">
                        <div class="detail-label">
                            <i class="fas fa-envelope"></i>
                            Email
                        </div>
                        <div class="detail-value">{payer_email}</div>
                    </div>
                    
                    <div class="detail-row">
                        <div class="detail-label">
                            <i class="fas fa-info-circle"></i>
                            Status
                        </div>
                        <div class="detail-value">{status}</div>
                    </div>
                    
                    <div class="detail-row">
                        <div class="detail-label">
                            <i class="fas fa-receipt"></i>
                            Order ID
                        </div>
                        <div class="detail-value">{order_id[:20]}...</div>
                    </div>
                </div>
                
                <div class="transaction-id">
                    <p><i class="fas fa-fingerprint"></i> Transaction ID</p>
                    <code>{transaction_id}</code>
                </div>
                
                <div class="receipt-actions">
                    <a href="/download-receipt/{transaction_id}" class="btn-receipt btn-download">
                        <i class="fas fa-download"></i> Download PDF
                    </a>
                    <button onclick="window.print()" class="btn-receipt btn-print">
                        <i class="fas fa-print"></i> Print Receipt
                    </button>
                </div>
                
                <a href="/" class="btn-home">
                    <i class="fas fa-home"></i> Make Another Payment
                </a>
            </div>
        </body>
        </html>
        '''
        return render_template_string(html)
        
    except Exception as e:
        return f"Error processing payment: {str(e)}", 500

@app.route('/download-receipt/<transaction_id>')
def download_receipt(transaction_id):
    try:
        if transaction_id not in receipt_data_store:
            return "Receipt not found", 404
        
        receipt_data = receipt_data_store[transaction_id]
        pdf_buffer = generate_pdf_receipt(receipt_data)
        
        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'receipt_{transaction_id}.pdf'
        )
    except Exception as e:
        return f"Error generating receipt: {str(e)}", 500

@app.route('/payment/cancel')
def payment_cancel():
    html = '''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Payment Cancelled</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                min-height: 100vh;
                display: flex;
                justify-content: center;
                align-items: center;
                padding: 20px;
            }
            
            .container {
                background: white;
                padding: 40px;
                border-radius: 20px;
                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
                max-width: 450px;
                width: 100%;
                text-align: center;
                animation: slideIn 0.5s ease-out;
            }
            
            @keyframes slideIn {
                from {
                    opacity: 0;
                    transform: scale(0.9);
                }
                to {
                    opacity: 1;
                    transform: scale(1);
                }
            }
            
            .cancel-icon {
                margin-bottom: 25px;
            }
            
            .cancel-icon i {
                font-size: 80px;
                color: #f5576c;
                animation: shake 0.5s ease-out;
            }
            
            @keyframes shake {
                0%, 100% { transform: translateX(0); }
                25% { transform: translateX(-10px); }
                75% { transform: translateX(10px); }
            }
            
            h1 {
                color: #333;
                font-size: 28px;
                margin-bottom: 15px;
            }
            
            p {
                color: #666;
                font-size: 16px;
                line-height: 1.6;
                margin-bottom: 30px;
            }
            
            .info-box {
                background: #fff3cd;
                border-left: 4px solid #ffc107;
                padding: 15px;
                border-radius: 10px;
                margin-bottom: 25px;
                text-align: left;
            }
            
            .info-box i {
                color: #ffc107;
                margin-right: 8px;
            }
            
            .info-box p {
                font-size: 14px;
                margin: 0;
                color: #856404;
            }
            
            .btn-home {
                display: inline-block;
                padding: 15px 40px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                text-decoration: none;
                border-radius: 10px;
                font-weight: 600;
                transition: all 0.3s ease;
            }
            
            .btn-home:hover {
                transform: translateY(-2px);
                box-shadow: 0 10px 25px rgba(102, 126, 234, 0.3);
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="cancel-icon">
                <i class="fas fa-times-circle"></i>
            </div>
            
            <h1>Payment Cancelled</h1>
            <p>You have cancelled the payment process. No charges have been made to your account.</p>
            
            <div class="info-box">
                <p>
                    <i class="fas fa-info-circle"></i>
                    <strong>Note:</strong> If you experienced any issues during checkout, please try again or contact support.
                </p>
            </div>
            
            <a href="/" class="btn-home">
                <i class="fas fa-redo"></i> Try Again
            </a>
        </div>
    </body>
    </html>
    '''
    return render_template_string(html)

if __name__ == '__main__':
    app.run(debug=True)