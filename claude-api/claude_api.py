import json
import os
import uuid
from enum import Enum

from typing import Dict, List, Optional, Union

import requests as req
import tzlocal
from curl_cffi import requests


class ContentType(Enum):
    PDF = 'application/pdf'
    TXT = 'text/plain'
    CSV = 'text/csv'
    OCTET_STREAM = 'application/octet-stream'

class Client:
    BASE_URL = "https://claude.ai/api"
    USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36'

    def __init__(self, cookie: str):
        self.cookie = cookie
        self.organization_id = self._get_organization_id()

    def _get_organization_id(self) -> str:
        url = f"{self.BASE_URL}/organizations"
        headers = self._get_headers()
        response = requests.get(url, headers=headers, impersonate="chrome110")
        response.raise_for_status()
        return response.json()[0]["uuid"]

    def _get_headers(self, extra_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {
            'User-Agent': self.USER_AGENT,
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://claude.ai/chats',
            'Content-Type': 'application/json',
            'Connection': 'keep-alive',
            'Cookie': self.cookie,
        }
        if extra_headers:
            headers.update(extra_headers)
        return headers

    @staticmethod
    def _get_content_type(file_path: str) -> str:
        extension = os.path.splitext(file_path)[-1].lower()
        return (
            ContentType[extension[1:].upper()].value
            if extension[1:].upper() in ContentType.__members__
            else ContentType.OCTET_STREAM.value
        )

    def list_all_conversations(self) -> List[Dict]:
        url = f"{self.BASE_URL}/organizations/{self.organization_id}/chat_conversations"
        response = requests.get(url, headers=self._get_headers(), impersonate="chrome110")
        response.raise_for_status()
        return response.json()

    def send_message(
        self,
        prompt: str,
        conversation_id: str,
        attachment: Optional[str] = None,
        timeout: int = 500,
        print_stream: bool = False,
    ) -> str:
        url = f"{self.BASE_URL}/organizations/{self.organization_id}/chat_conversations/{conversation_id}/completion"
        attachments = [self.upload_attachment(attachment)] if attachment else []
        
        payload = json.dumps(
            {"prompt": prompt, "timezone": tzlocal.get_localzone_name(), "attachments": attachments}
        )

        headers = self._get_headers({
            'Accept': 'text/event-stream, text/event-stream',
            'Origin': 'https://claude.ai',
            'DNT': '1',
            'TE': 'trailers',
        })

        response = requests.post(
            url,
            headers=headers,
            data=payload,
            impersonate="chrome110",
            timeout=timeout,
            stream=True,
        )
        return self._process_stream_response(response, print_stream)

    @staticmethod
    def _process_stream_response(response, print_stream: bool) -> str:
        gpt_response = []
        for line in response.iter_lines():
            if not line:
                continue
            decoded_line = line.decode('utf-8').strip()
            if not decoded_line.startswith('data: '):
                continue
            try:
                data = json.loads(decoded_line[6:])
                if data['type'] == 'completion':
                    completion = data['completion']
                    gpt_response.append(completion)
                    if print_stream:
                        print(completion, end="", flush=True)
            except json.JSONDecodeError:
                continue
        return "".join(gpt_response)

    def delete_conversation(self, conversation_id: str) -> bool:
        url = f"{self.BASE_URL}/organizations/{self.organization_id}/chat_conversations/{conversation_id}"
        response = requests.delete(
            url,
            headers=self._get_headers(),
            data=json.dumps(conversation_id),
            impersonate="chrome110",
        )
        return response.status_code == 204

    def chat_conversation_history(self, conversation_id: str) -> Dict:
        url = f"{self.BASE_URL}/organizations/{self.organization_id}/chat_conversations/{conversation_id}"
        response = requests.get(url, headers=self._get_headers(), impersonate="chrome110")
        response.raise_for_status()
        return response.json()

    @staticmethod
    def generate_uuid() -> str:
        return str(uuid.uuid4())

    def create_new_chat(self) -> Dict:
        url = f"{self.BASE_URL}/organizations/{self.organization_id}/chat_conversations"
        payload = json.dumps({"uuid": self.generate_uuid(), "name": ""})
        response = requests.post(
            url, headers=self._get_headers(), data=payload, impersonate="chrome110"
        )
        response.raise_for_status()
        return response.json()

    def reset_all(self) -> bool:
        conversations = self.list_all_conversations()
        for conversation in conversations:
            self.delete_conversation(conversation["uuid"])
        return True

    def upload_attachment(self, file_path: str) -> Union[Dict, bool]:
        if file_path.endswith('.txt'):
            return self._process_text_file(file_path)
        url = f'{self.BASE_URL}/convert_document'
        file_name = os.path.basename(file_path)
        content_type = self._get_content_type(file_path)

        files = {
            'file': (file_name, open(file_path, 'rb'), content_type),
            'orgUuid': (None, self.organization_id),
        }

        response = req.post(url, headers=self._get_headers(), files=files)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _process_text_file(file_path: str) -> Dict:
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        with open(file_path, 'r', encoding='utf-8') as file:
            file_content = file.read()
        return {
            "file_name": file_name,
            "file_type": ContentType.TXT.value,
            "file_size": file_size,
            "extracted_content": file_content,
        }

    def rename_chat(self, title: str, conversation_id: str) -> bool:
        url = f"{self.BASE_URL}/rename_chat"
        payload = json.dumps({
            "organization_uuid": self.organization_id,
            "conversation_uuid": conversation_id,
            "title": title,
        })
        response = requests.post(
            url, headers=self._get_headers(), data=payload, impersonate="chrome110"
        )
        return response.status_code == 200
