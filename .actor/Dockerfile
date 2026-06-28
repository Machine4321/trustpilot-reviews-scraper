# Use the official Apify Python base image
FROM apify/actor-python:3.11

# Copy requirements.txt first to leverage Docker cache
COPY requirements.txt ./

# Install python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy all files into the container
COPY . ./

# Run the actor source package
CMD ["python3", "-m", "src"]
