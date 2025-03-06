from shiny import App, reactive, render, ui, run_app
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt

# set pandas options
pd.options.display.max_columns = 10
pd.options.display.width = 120
pd.options.mode.copy_on_write = True

# define election years (not all supported)
election_years = [2012, 2016, 2020, 2024]

# load precincts shapes from ESRI shapefile
precincts = gpd.read_file("data/Clatsop_Precincts.shp")
precincts['Precinct_N'] = precincts['Precinct_N'].astype(int)

# UI definition
app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.input_select(
            "select_year",
            "Select Election Year",
            choices=election_years,
            selected='2024'
        ),
        ui.input_select("select_race",
                        "Select Election",
                        choices=[]),  # will be populated by the server function)
        width=350
    ),
    ui.output_plot("results_plot"),
    ui.card(
        ui.card_header("Election Results Details"),
        ui.output_data_frame("results_table")
    )
)


def server(input, output, session):
    @reactive.calc
    def calculate_results():
        election_results = pd.read_csv(f"data/{input.select_year()}_Clatsop_Precinct.csv")
        election_results = election_results[election_results['Race'] == input.select_race()]
        election_results = election_results[~election_results['Precinct'].str.contains('Total')]

        # Filter results for Democratic and Republican candidates
        major_parties = election_results[election_results['Party'].isin(['Democratic Party',
                                                                         'Republican Party'])]

        # Aggregate results for all minor parties and write-ins into a single 'Other' party
        minor_parties = election_results[~election_results['Party'].isin(['Democratic Party', 'Republican Party'])]
        minor_parties['Party'] = 'Other Party'
        minor_parties['Name'] = 'Other Candidate / Write-In'
        minor_parties = minor_parties.groupby(['Race', 'Precinct', 'PrecinctCode', 'Party'])[
            'Votes'].sum().reset_index()

        race_results = pd.concat([major_parties, minor_parties])

        # Calculate the percentage of votes for each candidate in each precinct
        race_results['VotePct'] = race_results.groupby(['Precinct'])['Votes'].transform(lambda x: x / x.sum())

        race_results.sort_values(by=['Precinct', 'Name'], inplace=True)

        return race_results

    @reactive.effect
    def select_year():
        df = pd.read_csv(f"data/{input.select_year()}_Clatsop_Precinct.csv")
        choices = list(df['Race'].unique())
        return ui.update_select("select_race", choices=choices, selected=choices[0])

    @render.plot
    def results_plot():
        race_results = calculate_results()

        # Pivot the data by party to have separate columns for Democratic, Republican and Other Party votes
        party_results = race_results.pivot_table(index=['Precinct', 'PrecinctCode'],
                                                 columns='Party',
                                                 values='VotePct').reset_index()

        # Name the columns
        party_results.rename(
            columns={'Democratic Party': 'DemVotePct',
                     'Republican Party': 'RepVotePct',
                     'Other Party': 'OtherPct'},
            inplace=True)

        # Calculate the margin of victory for each party
        party_results['DemMarginPct'] = party_results['DemVotePct'] - party_results['RepVotePct']
        party_results['RepMarginPct'] = party_results['RepVotePct'] - party_results['DemVotePct']

        # Merge the results with the precinct shapefile data
        precinct_data = precincts.merge(party_results, left_on='Precinct_N', right_on='PrecinctCode')

        # Plot the choropleth map
        fig, ax = plt.subplots(1, 1, figsize=(10, 10))
        ax.set_title('Percentage of Votes for Democratic vs Republican Candidates by Precinct')
        ax.set_axis_off()
        return precinct_data.plot(column='DemMarginPct',
                                  cmap='RdBu',
                                  edgecolor='black',
                                  linewidth=0.2,
                                  ax=ax,
                                  legend=True,
                                  alpha=1.0)

    @render.data_frame
    def results_table():
        df = calculate_results().copy()

        # format the percentage columns
        df['VotePct'] = df['VotePct'].map('{:.2%}'.format)

        return render.DataGrid(
            df,
            width="100%"
        )


app = App(app_ui, server)

if __name__ == '__main__':
    run_app('app:app', reload=True)
