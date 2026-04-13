# toks

Count tokens using tiktoken.

## Usage

```sh
toks file.txt
cat file.txt | toks
toks -e o200k_base file.txt
```

Encodings: `cl100k_base` (default, GPT-4/Claude), `o200k_base` (GPT-4o).
