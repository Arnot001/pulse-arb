def classify_opportunity(book_percentage, price_gap_percentage):
    """
    Returns:
    - opportunity_type
    - score out of 100
    """

    if book_percentage < 100:
        return "TRUE_ARB", 98

    if book_percentage <= 101:
        return "NEAR_ARB", 88

    if price_gap_percentage >= 8:
        return "PRICE_GAP", 72

    return "NORMAL", 35