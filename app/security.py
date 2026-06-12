import re
from typing import Dict, Tuple

class PIISecurityManager:
    def __init__(self):
        self.analyzer = None
        self.anonymizer = None
        self.use_presidio = False
        
        # Try importing and initializing Presidio. If it fails, use the Regex Engine.
        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_anonymizer import AnonymizerEngine
            self.analyzer = AnalyzerEngine()
            self.anonymizer = AnonymizerEngine()
            self.use_presidio = True
            print("[INFO] PIISecurityManager: Presidio Engine initialized successfully.")
        except Exception as e:
            print(f"[WARNING] PIISecurityManager: Presidio load failed ({e}). Falling back to Regex Masking Engine.")
            self.use_presidio = False

    def mask_pii(self, text: str) -> Tuple[str, Dict[str, str]]:
        """Scans input text, replaces PII with placeholder tokens, and returns the map."""
        if not text:
            return "", {}

        pii_mapping: Dict[str, str] = {}
        masked_text = text

        if self.use_presidio:
            try:
                # 1. Run Presidio Analyzer
                results = self.analyzer.analyze(text=text, language="en")
                
                # Filter out overlapping entities (conflict resolution)
                # Sort by span length descending first so we keep the longest match (e.g. full email over partial name)
                sorted_by_span = sorted(results, key=lambda x: x.end - x.start, reverse=True)
                
                consolidated_results = []
                for res in sorted_by_span:
                    # Check if this result overlaps with any already accepted result
                    overlap = False
                    for accepted in consolidated_results:
                        if not (res.end <= accepted.start or res.start >= accepted.end):
                            overlap = True
                            break
                    if not overlap:
                        consolidated_results.append(res)
                
                # Sort consolidated results by start position in descending order to avoid shift issues during string replacement
                sorted_results = sorted(consolidated_results, key=lambda x: x.start, reverse=True)
                
                email_idx = 1
                phone_idx = 1
                name_idx = 1
                misc_idx = 1
                
                for res in sorted_results:
                    entity_type = res.entity_type
                    start = res.start
                    end = res.end
                    raw_val = text[start:end]
                    
                    if entity_type == "EMAIL_ADDRESS":
                        token = f"[REDACTED_EMAIL_{email_idx}]"
                        email_idx += 1
                    elif entity_type == "PHONE_NUMBER":
                        token = f"[REDACTED_PHONE_{phone_idx}]"
                        phone_idx += 1
                    elif entity_type == "PERSON":
                        token = f"[REDACTED_NAME_{name_idx}]"
                        name_idx += 1
                    else:
                        token = f"[REDACTED_VAL_{misc_idx}]"
                        misc_idx += 1
                        
                    pii_mapping[token] = raw_val
                    masked_text = masked_text[:start] + token + masked_text[end:]
                
                # Also apply regex on top of Presidio for custom enterprise patterns (like API keys or Emp IDs)
                masked_text, custom_mapping = self._mask_custom_patterns(masked_text)
                pii_mapping.update(custom_mapping)
                
                return masked_text, pii_mapping
            except Exception as e:
                print(f"[ERROR] Presidio execution failed ({e}). Reverting to regex engine.")
                return self._mask_custom_patterns(text)
        else:
            return self._mask_custom_patterns(text)

    def _mask_custom_patterns(self, text: str) -> Tuple[str, Dict[str, str]]:
        """Regex-based fallback masking for standard entities and custom enterprise entities."""
        pii_mapping: Dict[str, str] = {}
        masked_text = text

        # Regex definitions
        patterns = {
            "EMAIL": r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
            "PHONE": r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}",
            "API_KEY": r"AT-SECURE-APIKEY-\w+",
            "EMP_ID": r"AT-EMP-\d{4}"
        }

        for p_type, regex in patterns.items():
            idx = 1
            while True:
                match = re.search(regex, masked_text)
                if not match:
                    break
                raw_val = match.group(0)
                token = f"[REDACTED_{p_type}_{idx}]"
                idx += 1
                
                pii_mapping[token] = raw_val
                masked_text = masked_text.replace(raw_val, token, 1)

        # Regex for Capitalized Names fallback (e.g. John Doe)
        # Match word sequences starting with Capital Letters (2 words, e.g. Marcus Sterling)
        name_regex = r"\b[A-Z][a-z]+\s[A-Z][a-z]+\b"
        # Avoid matching uppercase names if they are common words or part of titles,
        # but for demo fallback, it works. Let's filter out known noise.
        name_idx = 1
        matches = re.findall(name_regex, masked_text)
        for name in list(set(matches)):
            # Ignore standard UI / System keywords
            if name in ["Global Employee", "Paid Time", "Employee Portal", "Human Resources", "Global Employee", "Aura Tech", "AuraTech"]:
                continue
            token = f"[REDACTED_NAME_{name_idx}]"
            name_idx += 1
            pii_mapping[token] = name
            masked_text = masked_text.replace(name, token)

        return masked_text, pii_mapping

    def demask_pii(self, text: str, pii_mapping: Dict[str, str]) -> str:
        """Restores raw PII values by replacing tokens back with their original entities."""
        if not text or not pii_mapping:
            return text
        demasked = text
        for token, raw_val in pii_mapping.items():
            demasked = demasked.replace(token, raw_val)
        return demasked

# Instantiate singleton
pii_manager = PIISecurityManager()
