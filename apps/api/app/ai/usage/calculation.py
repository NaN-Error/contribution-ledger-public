"""Local standard-text usage estimates, not invoice accounting or a provider cap."""
SCALE=1_000_000
PROBE_INPUT_ALLOWANCE=2048
PROBE_OUTPUT_LIMIT=256

def token_cost(input_tokens:int,output_tokens:int,input_rate:int,output_rate:int)->int:
    values=(input_tokens,output_tokens,input_rate,output_rate)
    if any(type(x) is not int or x<0 for x in values):raise ValueError('Nonnegative integers required')
    # Round the combined nonnegative estimate up to a microdollar.
    return (input_tokens*input_rate+output_tokens*output_rate+SCALE-1)//SCALE
