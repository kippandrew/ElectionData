import typing
import pandas as pd

import pdfplumber

PARTIES = pd.read_csv('data/Parties.csv')


def extract_tables_from_pdf(path):
    tables = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            tables.extend(page.extract_tables(dict(text_line_dir_rotated="rtl",
                                                   text_char_dir_rotated="ttb",
                                                   text_keep_blank_chars=True)))
    return tables


def is_result_table(tbl):
    for row in tbl:
        if any([col == 'VOTE FOR 1' for col in row]) or any([col == 'VOTE FOR 2' for col in row]):
            return True
    return False


def parse_tally(tally: str):
    return int(tally.replace(',', ''))


def parse_precinct(precinct: str):
    p = precinct.replace('\n', ' ')
    tokens = p.split(' - ')
    if tokens and tokens[0].isnumeric():
        return dict(Precinct=p, PrecinctCode=int(tokens[0]))
    return dict(Precinct=p, PrecinctCode=None)


def parse_race(race: str):
    return race.replace('\n', ' ')


def parse_candidate(candidate: str):
    # remove newlines from the candidate name
    candidate = candidate.replace('\n', ' ')

    # search for a party code in the first token of the candidate name
    tokens = candidate.split()
    party = None
    if tokens[0] in PARTIES['Party code'].values:
        party = PARTIES[PARTIES['Party code'] == tokens[0]]['Party description'].values[0]
        candidate = ' '.join(tokens[1:])

    return dict(Name=candidate, Party=party)


def extract_tallies(tbl, race, index1, index2):
    # the list of candidates is in the first row of the table after the row that contains 'VOTE FOR 1'.
    # the tallies are in the columns that are between index1 and index2 in the rows that follow.

    offset = 2

    candidates = []
    for i, row in enumerate(tbl):
        if row[index1] == 'VOTE FOR 1' or row[index1] == 'VOTE FOR 2':
            candidates = [parse_candidate(c) for c in tbl[i + 1][index1:index2]]
            offset = i + 2
            break

    if not candidates:
        raise ValueError('No candidates found')

    for row in tbl[offset:]:
        for i, col in enumerate(row[index1:index2]):
            precinct = parse_precinct(row[0])
            tally = parse_tally(col) if col != '' else None

            yield dict(Race=parse_race(race), **precinct, **candidates[i], Votes=tally)


def extract_results(tbl):
    j = 1
    k = 1
    race = tbl[0][1]

    # it's possible that table contains tallies for more than on race. iterate through the header to find
    # the start and end columns for each race in the table. then extract the tallies in those columns.

    for i, col in enumerate(tbl[0]):

        if col is None:
            k = i
            continue

        if col != race:
            yield from extract_tallies(tbl, race, j, k)

            k = i - 1
            j = i
            race = col

    yield from extract_tallies(tbl, race, j, k)


if __name__ == '__main__':

    pdf_path = 'data/2024_Clatsop_Precinct.PDF'
    df = pd.DataFrame()

    tables = extract_tables_from_pdf(pdf_path)
    for table in tables:
        if is_result_table(table):
            results = list(extract_results(table))
            df = pd.concat([df, pd.DataFrame(results)])

    # print(df)
    print(df.to_string())

    df.to_csv('data/2024_Clatsop_Precinct.csv', index=False)
