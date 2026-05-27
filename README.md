# VidyaPath AI

An AI-powered personalized learning assistant that helps students learn smarter from uploaded PDFs and documents. The platform provides AI-generated summaries, quizzes, flashcards, chatbot interactions, and smart study assistance using Large Language Models (LLMs).

---

## Features

* 📄 Upload PDF and DOCX study materials
* 🤖 AI chatbot for document interaction
* 🧠 Smart notes and summaries generation
* ❓ Automatic quiz generation
* 🗂️ Flashcards creation for revision
* 🔐 User authentication system
* 📚 Personalized learning support
* 🎨 Interactive and responsive UI

---

## Technologies Used

### Backend

* Python
* Flask
* SQLAlchemy
* Flask-Migrate
* Flask-CORS

### Frontend

* HTML
* CSS
* JavaScript

### Database

* MySQL (XAMPP)

### AI & Processing

* Groq API
* PyPDF2
* pdfplumber
* python-docx

---

## Project Structure

```bash
VidyaPath-AI/
│── app.py
│── auth.py
│── model.py
│── vidyapath.sql
│── .env
│── templates/
│── static/
│── README.md
```

---

## Installation & Setup

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/VidyaPath-AI.git
cd VidyaPath-AI
```

---

### 2. Install Dependencies

Install the required Python packages:

```bash
pip install flask flask_sqlalchemy flask_migrate flask_cors python-dotenv sqlalchemy pymysql PyPDF2 python-docx pdfplumber groq
```

---

### 3. Setup MySQL Database (XAMPP)

* Start Apache and MySQL in XAMPP.
* Open phpMyAdmin.
* Import the provided `vidyapath.sql` file.

Run the following commands in XAMPP MySQL shell:

```sql
CREATE DATABASE IF NOT EXISTS vidyapath;
USE vidyapath;

CREATE USER 'vidya_user'@'localhost' IDENTIFIED BY 'VidyaPathAI2025';
CREATE USER 'vidya_user'@'127.0.0.1' IDENTIFIED BY 'VidyaPathAI2025';

GRANT ALL PRIVILEGES ON vidyapath.* TO 'vidya_user'@'localhost';
GRANT ALL PRIVILEGES ON vidyapath.* TO 'vidya_user'@'127.0.0.1';

FLUSH PRIVILEGES;
```

---

### 4. Configure Environment Variables

Create a `.env` file inside the project folder and add your credentials/API keys.

Example:

```env
GROQ_API_KEY=your_api_key
SECRET_KEY=your_secret_key
```

---

### 5. Run the Application

```bash
python app.py
```

The application will start on:

```bash
http://127.0.0.1:5000/
```

---

## Future Improvements

* 🌍 Multilingual support
* 📱 Mobile responsive enhancements
* 📊 Student progress tracking dashboard
* 🎙️ Voice-based learning assistant
* 🧭 AI-generated mind maps

---

## Author

Mohiba Ansari

---

## License

This project is licensed under the MIT License.
