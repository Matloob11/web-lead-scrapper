import base64

def decode_houzz_trk_link(url):
    if not url or "/trk/" not in url:
        return ""

    try:
        parts = url.split("/trk/")[1].split("/")
        if not parts:
            return ""

        encoded_segment = parts[0]
        print(f"Encoded segment: '{encoded_segment}', length: {len(encoded_segment)}")
        # Pad base64 if needed
        missing_padding = len(encoded_segment) % 4
        if missing_padding:
            encoded_segment += "=" * (4 - missing_padding)
            print(f"Padded segment: '{encoded_segment}', length: {len(encoded_segment)}")

        decoded = base64.b64decode(encoded_segment).decode("utf-8", errors="ignore")
        print(f"Decoded: '{decoded}'")
        if decoded.startswith("http"):
            return decoded
    except Exception as e:
        print(f"Error: {e}")
    return ""

test_url = "https://www.houzz.com/trk/aHR0cDovL3RlZG9yYS5vcmc/dc3a6bcdbd742d1dc32bc90462b4d73a/ue/MjUyMDc0MTY/ae7b5edc77558562c5734ce0e5bfbbc0"
print(f"Result: {decode_houzz_trk_link(test_url)}")

test_url_2 = "https://www.houzz.com/trk/aHR0cDovL3RyY3Jlbm92YXRpb25zaW5jLmNvbQ/99e4ab46634103412863da522d45b166/ue/MTUwNjA3NDY/6b087f979dba2a1f5fc15914e104d572"
print(f"Result 2: {decode_houzz_trk_link(test_url_2)}")
