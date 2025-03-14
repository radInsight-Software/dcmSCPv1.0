from dicomweb_client.api import DICOMwebClient

# Replace with your DICOMweb server URL
 

dicomweb_url = 'http://13.201.35.124:3010'

# If authentication is required, provide credentials
client = DICOMwebClient(url=dicomweb_url)

# Example: Query studies
studies = client.search_for_studies()
print(studies)