# StreamHub – Video Streaming Platform

A Flask-based video streaming web application that allows users to register, log in, upload videos, watch content, and manage their video library through a modern, responsive interface.

## 🚀 Features

- **User Authentication:** User registration and login.
- **Video Upload:** Upload videos with titles and descriptions.
- **Video Streaming:** Watch uploaded videos through the web interface.
- **Video Management:** Edit and delete your own videos.
- **Dashboard:** Manage your uploaded video collection.
- **Search:** Find videos using the available search functionality.
- **Admin Dashboard:** View registered users and recent uploaded videos.
- **Thumbnail Support:** Display video thumbnails where available.
- **Responsive UI:** Dark-themed interface for a modern viewing experience.
- **Database Integration:** Store application data using Flask-SQLAlchemy.

## 🛠️ Technologies Used

- Python
- Flask
- Flask-Login
- Flask-SQLAlchemy
- SQLite
- HTML5
- CSS3
- FFmpeg

## 📁 Project Structure

1. Video-Streaming-Platform
2. app.py
3. requirements.txt
4. .gitignore
5. README.md
6.static
│   1. css
       1. style.css
7. templates
    1. base.html
    2. index.html
    3. login.html
    4. register.html
    5. dashboard.html
    6. upload.html
    7. watch.html
    8. edit_video.html
    9. admin_dashboard.html


## ⚙️ Installation and Setup

### 1. Clone the repository

git clone  https://github.com/Payalpawar21/StreamHub-Video-Streaming-Platform.git


### 2. Open the project directory

cd StreamHub-Video-Streaming-Platform


### 3. Create a virtual environment

python -m venv venv


### 4. Activate the virtual environment

**Windows PowerShell:**

.\venv\Scripts\Activate.ps1


### 5. Install dependencies

python -m pip install -r requirements.txt


### 6. Configure environment variables

Create a `.env` file if required by your application. Configure the secret key, database URL, and admin email according to your local setup.

**Security:** Never commit `.env`, passwords, secret keys, or private credentials to GitHub.

### 7. Run the application

python app.py


Open the following URL in your browser:

http://127.0.0.1:5000/

## 🎬 How to Use

1. Register a new account.
2. Log in to the platform.
3. Open your dashboard.
4. Upload a video with a title and description.
5. Browse videos and open a video to watch it.
6. Edit or delete videos you own.
7. Access the admin dashboard using the configured admin account.

## 🔐 Security Notes

- Keep environment variables and credentials private.
- Use a strong, randomly generated secret key.
- Configure secure upload validation and file-size limits.
- Use production-ready settings before deploying publicly.

## 🔮 Future Improvements

- Video categories and playlists.
- Likes, comments, and ratings.
- User profile management.
- Video transcoding and adaptive streaming.
- Cloud storage integration.
- Deployment to a production hosting platform.

## 👩‍💻 Author

**Payal Pawar**

GitHub: https://github.com/Payalpawar21/StreamHub-Video-Streaming-Platform




