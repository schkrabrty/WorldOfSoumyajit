"""Exercise real payloads and cache boundaries without sending test API requests."""
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from media_descriptions import DescriptionError, MediaDescriptions


class DescriptionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "pages").mkdir()
        (self.root / "pages/example.html").write_text('---\ntitle: "My old trip"\n---\n<a data-title="Sunset over the lake"></a>')
        self.service = MediaDescriptions(self.root)
        self.environment = patch.dict(os.environ, {"OPENAI_API_KEY": "test-placeholder"})
        self.environment.start()
        self.addCleanup(self.environment.stop);self.addCleanup(self.temp.cleanup)

    def response(self):
        draft = dict(alt_text="A red bird on a branch.", title="Bird in the garden", description="A red bird perches in a leafy garden.", link_text="Garden guide (PDF)", notes="")
        return io.BytesIO(json.dumps({"output": [{"content": [{"type": "output_text", "text": json.dumps(draft)}]}]}).encode())

    def test_actual_image_style_context_and_cache_do_not_rewrite_content(self):
        original = (self.root / "pages/example.html").read_bytes()
        with patch('media_descriptions.urlopen', return_value=self.response()) as request:
            draft = self.service.describe({"url": "https://example.org/bird.jpg", "context": "Garden"})
            payload = json.loads(request.call_args[0][0].data)
            self.assertFalse(payload['store'])
            self.assertEqual(payload['input'][0]['content'][1]['image_url'], 'https://example.org/bird.jpg')
            self.assertIn('Sunset over the lake', payload['input'][0]['content'][0]['text'])
            self.assertEqual(draft['alt_text'], 'A red bird on a branch.')
            self.assertTrue(self.service.describe({"url": "https://example.org/bird.jpg"})['cached'])
            self.assertEqual(request.call_count, 1)
        self.assertEqual((self.root / "pages/example.html").read_bytes(), original)

    def test_staged_pdf_reads_only_matching_upload_and_sends_actual_file(self):
        folder = self.root / '.site-manager/uploads';folder.mkdir()
        identifier = 'a' * 24
        (folder / identifier).write_bytes(b'%PDF-1.7\nexample')
        (folder / (identifier + '.json')).write_text(json.dumps({'url': '/assets/uploads/example.pdf'}))
        value = self.service.source('/assets/uploads/example.pdf','pdf',identifier)
        self.assertEqual(value['type'],'input_file');self.assertTrue(value['file_data'].startswith('data:application/pdf;base64,'))
        with self.assertRaises(DescriptionError): self.service.source('/assets/uploads/other.pdf','pdf',identifier)
        with self.assertRaises(DescriptionError): self.service.source('/assets/%2e%2e/private.pdf','pdf')

    def test_private_urls_and_unsupported_image_formats_are_rejected(self):
        for url in ['http://127.0.0.1/private.jpg','http://[::1]/x','http://localhost/x','https://user:pass@example.org/x','https://example.org/a.svg']:
            with self.subTest(url=url),self.assertRaises(DescriptionError): self.service.source(url,'image')

    def test_video_is_explicitly_thumbnail_based_and_page_suggestions_use_writing(self):
        with patch('media_descriptions.urlopen', side_effect=lambda *args,**kwargs:self.response()) as request:
            video = self.service.describe({'kind':'video','url':'https://www.youtube.com/embed/abcdefghijk','context':'Garden video'})
            self.assertIn('not analyzed',video['basis'])
            self.assertIn('/abcdefghijk/hqdefault.jpg',json.loads(request.call_args[0][0].data)['input'][0]['content'][1]['image_url'])
            self.service.describe({'kind':'page','url':'example.html','context':'My garden walk'})
            content=json.loads(request.call_args[0][0].data)['input'][0]['content']
            self.assertEqual(len(content),1);self.assertIn('My garden walk',content[0]['text'])

    def test_provider_errors_never_echo_credentials(self):
        error=HTTPError('https://api.openai.com',401,'unauthorized',{},io.BytesIO(b'test-placeholder'))
        with patch('media_descriptions.urlopen',side_effect=error),self.assertRaises(DescriptionError) as raised:
            self.service.describe({'url':'https://example.org/photo.jpg'})
        self.assertNotIn('test-placeholder',str(raised.exception))

    def test_missing_key_preserves_editing_and_cached_drafts(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':''}):
            with self.assertRaisesRegex(DescriptionError,'existing OPENAI_API_KEY'): self.service.describe({'url':'https://example.org/photo.jpg'})

    def test_paper_text_fallback_has_an_honest_basis_and_does_not_claim_pdf_inspection(self):
        with patch('media_descriptions.urlopen',return_value=self.response()) as request:
            draft=self.service.describe({'kind':'pdf','url':'https://example.org/paper.pdf','source_text':'The paper evaluates remote spatial cognition.'})
            content=json.loads(request.call_args[0][0].data)['input'][0]['content']
            self.assertEqual(content[1]['type'],'input_text')
            self.assertIn('remote spatial cognition',content[1]['text'])
            self.assertIn('figures were not inspected',draft['basis'])

    def test_inventory_includes_video_topic_metadata_and_current_pdf_link_text(self):
        page={'id':'example.html','meta':{'title':'Spatial cognition','structured_data':{'@type':'VideoObject','embedUrl':'https://www.youtube.com/embed/abcdefghijk','name':'Remote AR research talk','description':'Two smartphone studies.'}},'body':'<iframe src="https://www.youtube.com/embed/abcdefghijk" title="Video"></iframe><a href="https://example.org/paper.pdf">Research paper (PDF)</a>'}
        result=self.service.inventory({'example.html':page},{},{})
        video=next(item for item in result['items'] if item['kind']=='video')
        self.assertIn('Remote AR research talk',video['context']);self.assertIn('Two smartphone studies.',video['context'])
        pdf=next(item for item in result['items'] if item['kind']=='pdf');self.assertEqual(pdf['current'],'Research paper (PDF)')


if __name__ == '__main__': unittest.main()
