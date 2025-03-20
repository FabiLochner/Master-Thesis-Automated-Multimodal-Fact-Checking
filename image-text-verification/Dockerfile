# Use Python 3.8 to match the repo's requirements
FROM python:3.8

# Install system dependencies (if needed, e.g., for building wheels)
RUN apt-get update && apt-get install -y build-essential

# Set a working directory
WORKDIR /app

# Copy all files and folders from the host to the container
COPY __pycache__ __pycache__/
COPY experiment.py extract_features.py LICENSE main.py model.py prepare_datasets.py README.md requirements.txt utils.py ./
COPY VERITE/ VERITE/


# Upgrade pip and install dependencies
RUN pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt


# Set the entrypoint to run the image downloading code.
# Assuming you want to run prepare_verite as a script
CMD ["python", "-c", "from prepare_datasets import prepare_verite; prepare_VERITE(download_images=True)"]


