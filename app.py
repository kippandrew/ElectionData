from shiny import App, reactive, render, ui, run_app
from shinywidgets import render_widget, output_widget
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt

# set pandas options
pd.options.display.max_columns = 10
pd.options.display.width = 120
pd.options.mode.copy_on_write = True

# define election years (not all supported)
election_years = [2024]

# load precincts shapes from ESRI shapefile
precincts = gpd.read_file("data/Clatsop_Precincts.shp")
precincts['Precinct_N'] = precincts['Precinct_N'].astype(int)

app_ui = ui.page_fillable(
    ui.card(
        ui.card_header("Election Results Explorer"),
        ui.layout_sidebar(
            ui.sidebar(
                ui.input_select(
                    "select_year",
                    "Select Election Year",
                    choices=election_years,
                    selected=2024
                ),
                ui.input_select("select_race",
                                "Select Election",
                                choices=[]),  # will be populated by the server function
                ui.input_radio_buttons(
                    "select_plot",
                    "Plot Type",
                    {
                        "candidate": "Candidate Results",
                        "party": "Party Results",
                        "turnout": "Turnout Results"
                    },
                ),
                width=350
            ),
            ui.card(
                ui.card_header("Election Results"),
                ui.output_plot("results_plot"),
            ),
            ui.card(
                ui.card_header("Election Results Details"),
                ui.output_data_frame("results_table")
            )
        )
    )
)


def is_partisan(results):
    return results['Party'].any()


def server(input, output, session):
    @reactive.calc
    def calculate_results():
        election_results = pd.read_csv(f"data/{input.select_year()}_Clatsop_Precinct.csv")
        election_results = election_results[election_results['Race'] == input.select_race()]
        election_results = election_results[~election_results['Precinct'].str.contains('Total')]

        if is_partisan(election_results):
            # Gather results for the two major parties
            major_parties = election_results[election_results['Party'].isin(['Democratic Party',
                                                                             'Republican Party'])]

            # Aggregate results for all minor parties and write-ins into a single row
            minor_parties = election_results[~election_results['Party'].isin(['Democratic Party',
                                                                              'Republican Party'])]
            minor_parties['Party'] = 'Other'
            minor_parties['Name'] = 'Other / Write-In'
            minor_parties = minor_parties.groupby(['Race',
                                                   'Precinct',
                                                   'PrecinctCode',
                                                   'Party',
                                                   'Name'])['Votes'].sum().reset_index()

            race_results = pd.concat([major_parties, minor_parties])

        else:

            race_results = election_results.copy()

        # Calculate the percentage of votes for each candidate in each precinct
        race_results['VotePct'] = race_results.groupby(['Precinct'])['Votes'].transform(lambda x: x / x.sum())

        race_results.sort_values(by=['Precinct', 'Name'], inplace=True)

        return race_results

    @reactive.effect
    def select_year():
        df = pd.read_csv(f"data/{input.select_year()}_Clatsop_Precinct.csv")
        choices = list(df['Race'].unique())
        return ui.update_select("select_race", choices=choices, selected=choices[0])

    def _plot_party(results):
        if not is_partisan(results):
            raise ValueError("The selected election is non-partisan. Please choose a different election.")

        # Pivot the data by party to have separate columns for Democratic, Republican and Other Party votes
        party_results = results.pivot_table(index=['Precinct', 'PrecinctCode'],
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
        ax.set_title('Precincts Results (by Party)')
        ax.set_axis_off()
        precinct_data.plot(column='DemMarginPct',
                                  cmap='RdBu',
                                  edgecolor='black',
                                  linewidth=0.2,
                                  ax=ax,
                                  legend=True,
                                  alpha=1.0)
        return fig

    @render.plot
    def results_plot():
        results = calculate_results()
        if input.select_plot() == 'party':
            return _plot_party(results)

    @render.data_frame
    def results_table():
        df = calculate_results().copy()

        # format the percentage columns
        df['VotePct'] = df['VotePct'].map('{:.2%}'.format)

        display_columns = ['Precinct', 'Name', 'Party', 'Votes', 'VotePct']

        return render.DataGrid(
            df[display_columns],
            width="100%"
        )


app = App(app_ui, server)

if __name__ == '__main__':
    run_app('app:app', reload=True)
